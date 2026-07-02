"""
LinkedIn Scraper using Playwright
- Requires saved session cookies (login helper must be run first)
- Scrapes posts from personal profiles (/in/...) and company pages (/company/...)
- Handles infinite scroll to load recent activity incrementally
- Uses URN ID sorting to bypass pinned posts and ensure the latest post is at index 0
- ⚠️  LinkedIn actively blocks scrapers — use responsibly
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse, urljoin

from playwright.async_api import Page

from app.models.schemas import PostItem, ScrapeResponse
from app.scrapers.playwright_base import run_playwright_scrape, save_debug_screenshot
from app.utils.date_parser import parse_relative_date

logger = logging.getLogger(__name__)


def _get_linkedin_posts_url(profile_url: str) -> str:
    """Build the correct posts feed URL for both personal and company pages."""
    url = profile_url.strip().rstrip("/")

    # Normalize country subdomains (in.linkedin.com, uk.linkedin.com, etc.)
    # to www.linkedin.com so cookies & auth work correctly
    url = re.sub(r'https?://(?!www\.)[a-z]{2,3}\.linkedin\.com',
                 'https://www.linkedin.com', url)

    # Company page → /posts/?feedView=all
    if "/company/" in url:
        # Extract: https://www.linkedin.com/company/SLUG
        match = re.search(r'(https://(?:www\.)?linkedin\.com/company/[^/?#]+)', url)
        if match:
            base = match.group(1).rstrip("/")
            return f"{base}/posts/?feedView=all"
        return url + "/posts/?feedView=all"

    # Personal profile → /recent-activity/all/
    if "/in/" in url:
        match = re.search(r'(https://(?:www\.)?linkedin\.com/in/[^/?#]+)', url)
        if match:
            base = match.group(1).rstrip("/")
            return f"{base}/recent-activity/all/"
        return url + "/recent-activity/all/"

    # School page
    if "/school/" in url:
        match = re.search(r'(https://(?:www\.)?linkedin\.com/school/[^/?#]+)', url)
        if match:
            base = match.group(1).rstrip("/")
            return f"{base}/posts/?feedView=all"

    # Fallback: append /posts/
    return url.rstrip("/") + "/posts/?feedView=all"


def _urn_to_url(urn: str) -> str | None:
    """Convert a LinkedIn URN string to a full post URL."""
    # urn:li:activity:1234567890
    m = re.search(r'urn:li:activity:(\d+)', urn)
    if m:
        return f"https://www.linkedin.com/feed/update/urn:li:activity:{m.group(1)}/"

    # urn:li:ugcPost:1234567890
    m = re.search(r'urn:li:ugcPost:(\d+)', urn)
    if m:
        return f"https://www.linkedin.com/feed/update/urn:li:ugcPost:{m.group(1)}/"

    # urn:li:share:1234567890
    m = re.search(r'urn:li:share:(\d+)', urn)
    if m:
        return f"https://www.linkedin.com/feed/update/urn:li:share:{m.group(1)}/"

    return None


def _extract_linkedin_sequence_id(url: str) -> int:
    """Extract the numeric sequence ID from a LinkedIn post URL."""
    # Matches: urn:li:activity:DIGITS, -activity-DIGITS, etc.
    m = re.search(r'(?:activity|ugcPost|share)[:\-](\d+)', url)
    if m:
        return int(m.group(1))
    # Fallback to any digits
    digits = re.findall(r'\d+', url)
    if digits:
        return int(digits[-1])
    return 0


async def _extract_linkedin_post_urls(page, max_posts: int) -> list[dict]:
    """
    Multi-strategy LinkedIn post URL extractor.
    Tries 4 different approaches in order. Returns first non-empty result.
    Each item in the returned list is a dict: {"url": str, "posted_at": str | None}
    """
    collected = []

    # ── STRATEGY 1: data-urn attribute on container divs ─────────────
    # Works for both personal and company pages (most reliable)
    try:
        urns_and_urls = await page.evaluate("""
            () => {
                const results = [];
                // Try multiple container types
                const selectors = [
                    '[data-urn*="activity"]',
                    '[data-urn*="ugcPost"]',
                    '[data-urn*="share"]',
                    'article[data-id]',
                    '.feed-shared-update-v2[data-urn]',
                    '.occludable-update[data-urn]',
                ];
                const seen = new Set();
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const urn = el.getAttribute('data-urn') || el.getAttribute('data-id');
                        if (urn && !seen.has(urn)) {
                            seen.add(urn);
                            
                            // Find any posts link inside this container
                            let postUrl = '';
                            const links = Array.from(el.querySelectorAll('a[href]'));
                            for (const a of links) {
                                const href = a.href || '';
                                if (href.includes('/posts/') || href.includes('/feed/update/urn:li:')) {
                                    postUrl = href;
                                    break;
                                }
                            }
                            
                            // Try to find sub-description/timestamp
                            const subDesc = el.querySelector('.feed-shared-actor__sub-description, [class*="sub-description"]');
                            let timeText = '';
                            if (subDesc) {
                                const hiddenSpan = subDesc.querySelector('.visually-hidden');
                                timeText = hiddenSpan ? hiddenSpan.innerText : subDesc.innerText;
                            }
                            
                            results.push({ urn, postUrl, timeText });
                        }
                    }
                }
                return results;
            }
        """)

        for item in urns_and_urls:
            if len(collected) >= max_posts:
                break
            
            url = item.get("postUrl")
            if url:
                # Clean URL: remove query parameters and hashes
                url = url.split('?')[0].split('#')[0].rstrip('/')
            else:
                url = _urn_to_url(item["urn"])
                
            if url:
                time_txt = item.get("timeText", "")
                posted_at = parse_relative_date(time_txt) if time_txt else None
                collected.append({"url": url, "posted_at": posted_at})

        if collected:
            return collected
    except Exception as e:
        logger.error(f"[LinkedIn] Strategy 1 failed: {e}")

    # ── STRATEGY 2: Scan all <a href> links matching post patterns ────
    # Fallback for pages where data-urn is not present
    try:
        links = await page.evaluate("""
            () => [...document.querySelectorAll('a[href]')].map(a => a.href)
        """)

        post_patterns = [
            r'linkedin\.com/feed/update/urn:li:[^"\'?\s]+',
            r'linkedin\.com/posts/[^"\'?\s]+',
            r'linkedin\.com/pulse/[^"\'?\s]+',
            r'linkedin\.com/company/[^/]+/posts/[^"\'?\s]*urn[^"\'?\s]*',
        ]
        seen = set()
        for link in links:
            if len(collected) >= max_posts:
                break
            for pattern in post_patterns:
                if re.search(pattern, link):
                    clean = link.split('?')[0].rstrip('/')
                    if clean not in seen:
                        seen.add(clean)
                        collected.append({"url": link, "posted_at": None})
                    break

        if collected:
            return collected
    except Exception as e:
        logger.error(f"[LinkedIn] Strategy 2 failed: {e}")

    # ── STRATEGY 3: Extract from page source (nuclear option) ─────────
    # For cases where Playwright can't access DOM properly
    try:
        content = await page.content()
        # Find all activity URNs embedded in the page source
        urns_found = re.findall(r'urn:li:activity:\d+', content)
        urns_found += re.findall(r'urn:li:ugcPost:\d+', content)
        seen = set()
        for urn in urns_found:
            if len(collected) >= max_posts:
                break
            if urn not in seen:
                seen.add(urn)
                url = _urn_to_url(urn)
                if url:
                    collected.append({"url": url, "posted_at": None})

        if collected:
            return collected
    except Exception as e:
        logger.error(f"[LinkedIn] Strategy 3 failed: {e}")

    return collected  # Empty


async def _scrape_linkedin_page(page: Page, url: str, max_posts: int) -> list[PostItem]:
    posts: list[PostItem] = []

    # 1. Build correct destination URL
    posts_url = _get_linkedin_posts_url(url)
    logger.info(f"LinkedIn target URL: {posts_url}")

    # Inject clipboard spy before navigation
    await page.add_init_script("""
        window.__copiedText = "";
        navigator.clipboard.writeText = async (text) => {
            window.__copiedText = text;
            return Promise.resolve();
        };
    """)

    # 2. Navigate with proper wait (60s timeout for slow connections)
    await page.goto(posts_url, wait_until="domcontentloaded", timeout=60000)
    
    # Wait for React hydration — look for the feed container OR posts list
    try:
        await page.wait_for_selector(
            "main, [role='main'], .scaffold-layout__main",
            timeout=20000
        )
    except Exception:
        pass  # Continue anyway — some layouts don't have this

    # Extra buffer for lazy-loaded post cards (LinkedIn hydration is slow)
    await page.wait_for_timeout(6000)

    # 3. Auth wall check (wait for potential redirect to resolve)
    for i in range(10):
        current_url = page.url
        if "/login" not in current_url and "/authwall" not in current_url and "/checkpoint" not in current_url:
            break
        logger.info(f"⏳ Waiting for LinkedIn auth redirect to resolve... ({i+1}/10) Current: {current_url}")
        await page.wait_for_timeout(1500)

    current_url = page.url
    if "linkedin.com/login" in current_url or "authwall" in current_url or "checkpoint" in current_url:
        raise ValueError(
            "LinkedIn redirected to login/authwall. "
            "Session cookies are expired. "
            "Fix: python -m app.tools.login_helper linkedin"
        )

    # Check for chrome error page (network failure, DNS issues, etc.)
    if current_url.startswith("chrome-error://") or current_url == "about:blank":
        raise RuntimeError(
            f"LinkedIn page failed to load (landed on {current_url}). "
            "This usually means cookies expired or network issue. "
            "Fix: python -m app.tools.login_helper linkedin"
        )

    await save_debug_screenshot(page, "linkedin_loaded")

    # 4. Scroll and collect progressively
    collected_posts = []
    seen = set()
    for scroll_round in range(6):
        await page.evaluate("window.scrollTo(0, (document.body || document.documentElement).scrollHeight)")
        await page.wait_for_timeout(2500)

        new_items = await _extract_linkedin_post_urls(page, max_posts * 3)
        for item in new_items:
            u = item["url"]
            clean = u.split("?")[0].rstrip("/")
            if clean not in seen:
                seen.add(clean)
                collected_posts.append(item)

        if len(collected_posts) >= max_posts:
            break

    await save_debug_screenshot(page, "linkedin_scrolled")

    # 5. Sort chronologically (highest sequence ID = newest)
    collected_posts.sort(key=lambda x: _extract_linkedin_sequence_id(x["url"]), reverse=True)

    # 6. Fail loudly if nothing found
    if not collected_posts:
        title = await page.title()
        content = await page.content()
        logger.error(f"LinkedIn 0 posts. URL={page.url} Title={title}")
        logger.error(f"HTML preview: {content[:2000]}")
        await save_debug_screenshot(page, "linkedin_zero_posts")
        raise RuntimeError(
            f"LinkedIn: 0 posts found on {posts_url}. "
            f"Page title: '{title}'. "
            "Check debug screenshot and session cookies. "
            "Fix: python -m app.tools.login_helper linkedin"
        )

    # 7. Try to resolve descriptive URLs using copy link dropdown option
    resolved_posts = []
    for item in collected_posts[:max_posts]:
        u = item["url"]
        posted_at = item["posted_at"]
        # If it's already a posts/ descriptive URL, keep it
        if "/posts/" in u and "activity-" in u:
            resolved_posts.append({"url": u, "posted_at": posted_at})
            continue
            
        seq_id = _extract_linkedin_sequence_id(u)
        if not seq_id:
            resolved_posts.append({"url": u, "posted_at": posted_at})
            continue
            
        desc_url = None
        try:
            container = await page.query_selector(f'[data-urn*="{seq_id}"], [data-id*="{seq_id}"]')
            if container:
                trigger = await container.query_selector("button.feed-shared-control-menu__trigger, button[aria-label*='control menu'], button[aria-label*='more options']")
                if trigger:
                    await trigger.click()
                    await page.wait_for_timeout(1000)
                    
                    # Click copy button
                    copy_btn = await page.query_selector(".option-share-via, li.option-share-via div[role='button'], .feed-shared-control-menu__dropdown-item:has-text('Copy link to post')")
                    if copy_btn:
                        await copy_btn.click()
                        await page.wait_for_timeout(1000)
                        copied = await page.evaluate("window.__copiedText")
                        if copied and "/posts/" in copied:
                            # Clean it
                            desc_url = copied.split('?')[0].split('#')[0].rstrip('/')
                            logger.info(f"✅ Resolved descriptive URL for {seq_id} -> {desc_url}")
                    
                    # Close menu if copy not found/completed
                    if not desc_url:
                        await trigger.click()
                        await page.wait_for_timeout(500)
        except Exception as e:
            logger.debug(f"Failed to copy link via UI dropdown for {seq_id}: {e}")
            
        resolved_posts.append({"url": desc_url or u, "posted_at": posted_at})

    # 8. Build PostItem objects
    for item in resolved_posts:
        posts.append(PostItem(
            post_url=item["url"],
            caption=None,
            thumbnail_url=None,
            posted_at=item["posted_at"],
            likes=None,
            platform="linkedin",
        ))

    logger.info(f"LinkedIn: found {len(posts)} posts. Latest: {posts[0].post_url}")
    return posts


async def scrape_linkedin(url: str, max_posts: int = 20) -> ScrapeResponse:
    """
    Scrape latest posts from a LinkedIn profile or company page.

    ⚠️  LinkedIn actively detects and blocks automated scraping.
    Use saved session cookies from a real browser login.
    """
    posts: list[PostItem] = []
    error_msg: Optional[str] = None

    try:
        posts = await run_playwright_scrape(
            platform="linkedin",
            scrape_fn=lambda page: _scrape_linkedin_page(page, url, max_posts),
        )
    except ValueError:
        raise
    except Exception as e:
        logger.exception(f"LinkedIn scraping failed: {e}")
        if not posts:
            raise RuntimeError(f"LinkedIn scraping failed: {e}")
        error_msg = str(e)

    return ScrapeResponse(
        platform="linkedin",
        profile_url=url,
        posts_found=len(posts),
        posts=posts,
        scrape_status="success" if not error_msg else "partial",
        message=error_msg or (
            "Note: LinkedIn may limit visible posts. "
            "Captions may be truncated to 500 chars."
            if posts else None
        ),
    )
