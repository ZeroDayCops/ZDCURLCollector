"""
Instagram Scraper using Playwright
- Uses saved session cookies (login helper must be run first)
- Scrapes public profile/page posts
- Handles infinite scroll to load more posts incrementally to bypass virtualization
"""

import logging
import re
from typing import Optional

from playwright.async_api import Page

from app.models.schemas import PostItem, ScrapeResponse
from app.scrapers.playwright_base import run_playwright_scrape, save_debug_screenshot

logger = logging.getLogger(__name__)


def shortcode_to_id(shortcode: str) -> int:
    """
    Decode an Instagram shortcode back into its numeric Media ID.
    Instagram shortcodes are base64url-encoded values of the Media ID.
    The Media ID is a Snowflake ID containing the creation timestamp in its higher bits.
    """
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    try:
        for char in shortcode:
            media_id = media_id * 64 + alphabet.index(char)
        return media_id
    except ValueError:
        return 0


def shortcode_to_timestamp(shortcode: str) -> float:
    """Extract creation timestamp from Instagram shortcode using its Media ID."""
    media_id = shortcode_to_id(shortcode)
    if not media_id:
        return 0.0
    instagram_epoch = 1314220021721
    timestamp_ms = (media_id >> 23) + instagram_epoch
    return timestamp_ms / 1000.0


async def _scrape_instagram_page(page: Page, url: str, max_posts: int) -> list[PostItem]:
    """Core scraping logic for an Instagram profile."""
    seen_urls: set = set()
    temp_posts: list[PostItem] = []

    logger.info(f"🌐 Navigating to Instagram: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=40000)
    await page.wait_for_timeout(3000)

    # Check if redirected to login page
    current_url = page.url
    if "accounts/login" in current_url or "two_factor" in current_url:
        raise ValueError(
            "Instagram redirected to login page. "
            "Your session cookies may be expired or missing. Re-run: python -m app.tools.login_helper instagram"
        )

    # Wait for post elements to render (Instagram is heavily client-side rendered)
    try:
        logger.info("⏳ Waiting for post selectors to appear...")
        await page.wait_for_selector('a[href*="/p/"], a[href*="/reel/"], a[href*="/reels/"]', timeout=10000)
        logger.info("✅ Post selectors appeared.")
    except Exception as e:
        logger.warning(f"⚠️ Timeout waiting for post links: {e}. Profile might be empty or loading slowly.")
        raise RuntimeError(f"Timeout waiting for Instagram post links to appear: {e}")

    await save_debug_screenshot(page, "instagram_loaded")

    # We scroll and collect incrementally to avoid losing posts to DOM virtualization
    scroll_count = max(3, max_posts // 3)
    logger.info(f"⚡ Starting incremental scroll-and-collect loop ({scroll_count} scrolls)...")

    for scroll in range(scroll_count + 1):
        extracted_items = await page.evaluate("""
            () => {
                const elements = Array.from(document.querySelectorAll('main a[href*="/p/"], main a[href*="/reel/"], main a[href*="/reels/"]'));
                return elements.map(el => {
                    const img = el.querySelector('img');
                    return {
                        href: el.href,
                        alt: img ? img.getAttribute('alt') : null,
                        src: img ? img.getAttribute('src') : null
                    };
                });
            }
        """)

        # Parse and collect newly discovered items
        for item in extracted_items:
            url_path = item.get("href")
            if not url_path:
                continue

            # Normalize URL to standard format (e.g. https://www.instagram.com/p/SHORTCODE/)
            match = re.search(r'/(p|reel)/([A-Za-z0-9_-]+)', url_path)
            if not match:
                # Fallback for /reels/shortcode
                match = re.search(r'/reels/([A-Za-z0-9_-]+)', url_path)
                if not match:
                    continue
                post_type = "reel"
                shortcode = match.group(1)
            else:
                post_type = match.group(1)
                shortcode = match.group(2)

            # Normalize p to post for schemas
            normalized_type = "post" if post_type == "p" else "reel"
            clean_url = f"https://www.instagram.com/{post_type}/{shortcode}/"

            if clean_url in seen_urls:
                continue

            seen_urls.add(clean_url)
            seen_urls.add(url_path)

            caption = item.get("alt")
            thumbnail_url = item.get("src")

            posted_at = None
            try:
                from datetime import datetime, timezone
                ts = shortcode_to_timestamp(shortcode)
                if ts > 0:
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    posted_at = dt.strftime('%Y-%m-%d %H:%M UTC')
            except Exception:
                pass

            temp_posts.append(PostItem(
                post_url=clean_url,
                caption=caption if caption else None,
                thumbnail_url=thumbnail_url if thumbnail_url else None,
                posted_at=posted_at,
                likes=None,
                platform="instagram",
                type=normalized_type,
            ))
            logger.info(f"  ✓ Found Instagram item: {clean_url} (Type: {normalized_type})")

        # Scroll down incrementally
        if scroll < scroll_count:
            await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
            await page.wait_for_timeout(2500)

    await save_debug_screenshot(page, "instagram_scrolled")

    if not temp_posts:
        raise RuntimeError("No Instagram posts found (profile might be restricted or empty)")

    # Sort all extracted items chronologically by Media ID (newest first)
    def get_sort_key(post_item: PostItem) -> int:
        parts = post_item.post_url.rstrip('/').split('/')
        shortcode_val = parts[-1]
        return shortcode_to_id(shortcode_val)

    logger.info(f"Total extracted {len(temp_posts)} items. Sorting chronologically.")
    temp_posts.sort(key=get_sort_key, reverse=True)

    # Slice the sorted results to the user's requested amount
    posts = temp_posts[:max_posts]
    for p in posts:
        logger.info(f"  ✓ Selected Instagram post: {p.post_url} (Type: {p.type})")

    return posts


async def scrape_instagram(url: str, max_posts: int = 20) -> ScrapeResponse:
    """Scrape latest posts from an Instagram profile URL."""
    posts: list[PostItem] = []
    error_msg: Optional[str] = None

    try:
        posts = await run_playwright_scrape(
            platform="instagram",
            scrape_fn=lambda page: _scrape_instagram_page(page, url, max_posts),
        )
    except ValueError:
        raise
    except Exception as e:
        logger.exception(f"Instagram scraping failed: {e}")
        if not posts:
            raise RuntimeError(f"Instagram scraping failed: {e}")
        error_msg = str(e)

    return ScrapeResponse(
        platform="instagram",
        profile_url=url,
        posts_found=len(posts),
        posts=posts,
        scrape_status="success" if not error_msg else "partial",
        message=error_msg,
    )
