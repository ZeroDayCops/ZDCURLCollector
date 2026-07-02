import logging
import re
from typing import Optional
from urllib.parse import urljoin

from playwright.async_api import Page

from app.models.schemas import PostItem, ScrapeResponse
from app.scrapers.playwright_base import run_playwright_scrape
from app.utils.date_parser import parse_relative_date

logger = logging.getLogger(__name__)


async def _scrape_fb_page(page: Page, url: str, max_posts: int) -> list[dict]:
    """
    Core scraping logic for Facebook using Modern Desktop layout.
    """
    # 1. URL Normalization: Ensure www.facebook.com is used
    target_url = url.replace("mbasic.facebook.com", "www.facebook.com").replace("m.facebook.com", "www.facebook.com")
    logger.info(f"🌐 Normalizing Facebook target URL: {url} -> {target_url}")

    # 2. Aggressive Network Interception: Relies on base class's asset blocker
    # (keeps stylesheets for layout rendering, blocks images/media/fonts)
    logger.info("🚫 Relying on base class network route interceptor to block images, media, and fonts.")

    # 3. Navigate & SPA Lazy Loading
    logger.info(f"🌐 Navigating to Facebook: {target_url}")
    await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)

    # Dismiss any dialog/login popups
    popups = [
        '[aria-label="Close"]',
        '[aria-label="Dismiss"]',
        'div[role="dialog"] [aria-label="Close"]',
        'div[role="dialog"] i.x',
        'div[role="dialog"] [role="button"]:has-text("Close")',
        'div[role="dialog"] [role="button"]:has-text("Dismiss")',
        '[role="button"]:has-text("Not Now")',
    ]
    
    async def dismiss_popups():
        for sel in popups:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    logger.info(f"Dismissing popup with selector: {sel}")
                    await el.click()
                    await page.wait_for_timeout(1000)
            except Exception as e:
                logger.debug(f"Popup dismissal failed for selector '{sel}': {e}")
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(200)
        except Exception:
            pass

    await dismiss_popups()

    # Press PageDown 3 times to trigger React lazy-loading
    logger.info("Executing PageDown lazy-loading loops to render React feed...")
    for i in range(3):
        await page.keyboard.press("PageDown")
        await page.wait_for_timeout(2000)
        # Check and dismiss popup again in case it appeared during scroll
        await dismiss_popups()

    # 4. ARIA Role Targeting: Get all article elements
    articles = await page.get_by_role("article").all()
    logger.info(f"Found {len(articles)} article containers on page.")

    # 5. Regex Link Extraction
    date_regex = re.compile(
        r"(\d+[hdm])|Yesterday|Just now|(\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))|\d{4}",
        re.IGNORECASE
    )
    # Robust fallback date/time patterns for Facebook Desktop (e.g. "2 hrs", "June 24", "June 24 at 10:24 AM")
    fallback_regex = re.compile(
        r"(\d+\s*(h|hr|hour|hours|hrs|m|min|minute|minutes|mins|d|day|days|w|week|weeks)\b)|"
        r"((jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2})|"
        r"(\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)|"
        r"yesterday|today|just now",
        re.IGNORECASE
    )

    raw_posts = []
    seen_urls = set()

    for idx, article in enumerate(articles, 1):
        try:
            # Find all <a href> tags in this article container
            anchors = await article.locator("a").all()
            date_anchor = None
            raw_date = ""

            for anchor in anchors:
                text = (await anchor.inner_text() or "").strip()
                aria_label = (await anchor.get_attribute("aria-label") or "").strip()

                # Check if inner text or aria-label matches the date/time regex
                if text and (date_regex.search(text) or fallback_regex.search(text)):
                    date_anchor = anchor
                    raw_date = text
                    break
                elif aria_label and (date_regex.search(aria_label) or fallback_regex.search(aria_label)):
                    date_anchor = anchor
                    raw_date = aria_label
                    break

            if not date_anchor:
                continue

            href = await date_anchor.get_attribute("href")
            if not href:
                continue

            # 6. Data Cleanup
            # Ensure absolute URL
            abs_url = urljoin("https://www.facebook.com", href)
            # Remove trackers/parameters (split at '?')
            clean_url = abs_url.split("?")[0]

            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            # Get raw text snippet of the post, ignoring standard UI buttons
            article_text = await article.inner_text() or ""
            lines = [line.strip() for line in article_text.split("\n") if line.strip()]

            ignored_lines = {
                "like", "comment", "share", "write a comment...", "send message", "message",
                "share as post", "send in whatsapp", "reactions", "most relevant", "view more comments",
                "active", "online", "joined", "follow", "interested", "log in", "sign up", "learn more",
                "reply", "view replies", "send", "gift", "comment as", "press enter to post."
            }

            cleaned_lines = []
            for line in lines:
                ll = line.lower()
                if ll in ignored_lines:
                    continue
                # Skip the raw date string itself to keep snippet clean
                if line == raw_date:
                    continue
                # Skip numeric lines that likely denote reactions/comments count
                if ll.isdigit() or re.match(r'^\d+(\.\d+)?[km]$', ll):
                    continue
                cleaned_lines.append(line)

            caption = " ".join(cleaned_lines)[:300].strip() or None

            # Pass raw date to date_parser utility
            parsed_date = parse_relative_date(raw_date)

            raw_posts.append({
                "platform": "facebook",
                "url": clean_url,
                "date": parsed_date,
                "raw_date": raw_date,
                "caption": caption
            })
            logger.info(f"  ✓ Extracted post {len(raw_posts)}: {clean_url} | Date: {parsed_date} (raw: {raw_date})")

            if len(raw_posts) >= max_posts:
                break

        except Exception as e:
            logger.warning(f"Failed to parse article {idx}: {e}")
            continue

    return raw_posts


async def scrape_facebook(url: str, max_posts: int = 20) -> ScrapeResponse:
    """Scrape latest posts from a Facebook profile or page using Apify as primary and Playwright as fallback."""
    posts: list[PostItem] = []
    error_msg: Optional[str] = None
    
    # Check for APIFY_TOKEN in env
    import os
    apify_token = os.getenv("APIFY_TOKEN", "").strip()
    if not apify_token:
        raise ValueError("APIFY_TOKEN environment variable is not configured")

    try:
        import httpx
        apify_url = f"https://api.apify.com/v2/acts/apify~facebook-posts-scraper/run-sync-get-dataset-items?token={apify_token}"
        payload = {
            "startUrls": [{"url": url}],
            "resultsLimit": max_posts,
            "viewOption": "posts"
        }
        
        logger.info(f"🚀 [Apify] Running Facebook Scraper for: {url}")
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(apify_url, json=payload)
            if response.status_code not in (200, 201):
                raise RuntimeError(f"Apify returned status {response.status_code}: {response.text}")
            
            data = response.json()
            logger.info(f"✅ [Apify] Facebook Scraper success! Found {len(data)} items for {url}")
            
            for item in data:
                post_url = item.get("url") or item.get("postUrl")
                if not post_url:
                    continue
                caption = item.get("text") or item.get("caption") or ""
                posted_at = item.get("time") or item.get("date") or ""
                
                # Parse date to standardized format if possible
                from app.utils.date_parser import parse_relative_date
                parsed_date = parse_relative_date(posted_at) if posted_at else ""
                
                posts.append(PostItem(
                    post_url=post_url,
                    caption=caption[:300].strip() if caption else None,
                    posted_at=parsed_date or posted_at,
                    platform="facebook",
                    type="post"
                ))
                
                if len(posts) >= max_posts:
                    break
    except Exception as e:
        logger.warning(f"⚠️ Apify Facebook scraping failed: {e}. Falling back to local Playwright desktop scraper...")
        try:
            raw_posts = await run_playwright_scrape(
                platform="facebook",
                scrape_fn=lambda page: _scrape_fb_page(page, url, max_posts),
            )
            posts = [] # clear any partial posts
            for p in raw_posts:
                posts.append(PostItem(
                    post_url=p["url"],
                    caption=p["caption"],
                    posted_at=p["date"],
                    platform=p["platform"],
                    type="post"
                ))
            error_msg = None # Clear error if fallback succeeds
        except Exception as fallback_err:
            logger.exception(f"Facebook local Playwright fallback also failed: {fallback_err}")
            if not posts:
                raise RuntimeError(f"Both Apify and local Playwright Facebook scraping failed: {fallback_err}")
            error_msg = f"Apify failed: {e}. Fallback failed: {fallback_err}"

    return ScrapeResponse(
        platform="facebook",
        profile_url=url,
        posts_found=len(posts),
        posts=posts,
        scrape_status="success" if not error_msg else "partial",
        message=error_msg,
    )
