"""
Pinterest Scraper using Playwright
- Public boards only (no login required)
- Scrapes pins from a user profile or specific board
- Handles Pinterest's virtual scroll / lazy loading
- Routes to /_created/ tab for original pins (not saved/board pins)
"""

import logging
import re
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import Page

from app.models.schemas import PostItem, ScrapeResponse
from app.scrapers.playwright_base import run_playwright_scrape, save_debug_screenshot
from app.utils.platform_detector import extract_username

logger = logging.getLogger(__name__)


def normalize_pinterest_url(url: str) -> str:
    """Normalize a Pinterest profile URL to have a trailing slash.
    Also normalizes country subdomains (in.pinterest.com -> www.pinterest.com).
    """
    url = url.strip().rstrip("/")
    # Normalize country subdomains: in.pinterest.com, uk.pinterest.com, etc.
    url = re.sub(r'https?://(?!www\.)[a-z]{2,3}\.pinterest\.',
                 'https://www.pinterest.', url)
    if "/pin/" in url:
        return url
    return url + "/"


def _build_created_url(profile_url: str) -> str:
    """Build a direct URL to the /_created/ tab of a Pinterest profile."""
    parsed = urlparse(profile_url)
    path = parsed.path.rstrip("/")
    # Remove /_saved or /_created if already present
    path = re.sub(r'/_(saved|created)$', '', path)
    return f"https://www.pinterest.com{path}/_created/"


def _extract_username_from_url(url: str) -> str:
    """Extract the Pinterest username from a profile URL."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p and not p.startswith("_")]
    return parts[0] if parts else ""


async def _scrape_pinterest_page(page: Page, url: str, max_posts: int) -> list[PostItem]:
    """Core Pinterest scraping logic for public boards."""
    from urllib.parse import urlparse
    posts: list[PostItem] = []
    seen_urls: set = set()

    username = _extract_username_from_url(url)

    # Strategy A: Navigate DIRECTLY to /_created/ URL (most reliable for original pins)
    created_url = _build_created_url(url)
    logger.info(f"🌐 Navigating directly to Pinterest Created tab: {created_url}")
    await page.goto(created_url, wait_until="domcontentloaded", timeout=40000)
    await page.wait_for_timeout(5000)

    # Check for login gate (Pinterest shows a modal)
    await _dismiss_login_modal(page)

    await save_debug_screenshot(page, "pinterest_created_direct")

    # Wait for pin content to appear (Pinterest hydration is slow)
    try:
        await page.wait_for_selector('a[href*="/pin/"]', timeout=8000)
        logger.info("✅ Pin links appeared on Created tab")
    except Exception:
        logger.warning("⚠️ No pin links found on direct /_created/ navigation")

    # Extract pins from the Created tab
    pins = await _extract_pins_from_page(page)
    logger.info(f"📋 Found {len(pins)} pins on direct /_created/ URL")

    # Strategy B: If _created gave 0, try the base profile URL
    if not pins:
        logger.info(f"🌐 Created tab empty, trying base profile: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(4000)
        await _dismiss_login_modal(page)

        # Try clicking the "Created" tab link
        try:
            created_tab = await page.query_selector(
                'a[href*="/_created"], [data-test-id="created-tab"]'
            )
            if created_tab:
                logger.info("📋 Clicking 'Created' tab link...")
                await created_tab.click()
                await page.wait_for_timeout(5000)
                try:
                    await page.wait_for_selector('a[href*="/pin/"]', timeout=8000)
                except Exception:
                    pass
                pins = await _extract_pins_from_page(page)
                logger.info(f"📋 Found {len(pins)} pins after clicking Created tab")
        except Exception as e:
            logger.debug(f"Created tab click failed: {e}")

    # Strategy C: Navigate into the first board
    if not pins:
        logger.info("📋 No pins on Created tab, trying first board fallback...")
        await save_debug_screenshot(page, "pinterest_no_created")

        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) >= 1:
            board_username = path_parts[0]
            # Find all board links (format: /username/board-name/)
            board_links = await page.evaluate(f"""
                () => {{
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    const username = "{board_username}".toLowerCase();
                    const boards = [];
                    for (let a of links) {{
                        const href = a.href;
                        if (!href) continue;
                        try {{
                            const urlObj = new URL(href);
                            const pathParts = urlObj.pathname.split('/').filter(Boolean);
                            if (pathParts.length === 2 && pathParts[0].toLowerCase() === username) {{
                                const boardName = pathParts[1].toLowerCase();
                                if (!["_created", "_saved", "_pins", "_boards", "feedback", "pins", "saved", "created"].includes(boardName)) {{
                                    boards.push(href);
                                }}
                            }}
                        }} catch (e) {{}}
                    }}
                    return boards;
                }}
            """)
            if board_links:
                first_board = board_links[0]
                logger.info(f"📋 Found {len(board_links)} boards. Navigating to first board: {first_board}")
                await page.goto(first_board, wait_until="domcontentloaded", timeout=40000)
                await page.wait_for_timeout(4000)
                await _dismiss_login_modal(page)
                await save_debug_screenshot(page, "pinterest_board_loaded")
                pins = await _extract_pins_from_page(page)
                logger.info(f"📋 Found {len(pins)} pins in first board")

    # Strategy D: Page source fallback if DOM extraction still got 0 pins
    if not pins:
        logger.warning("⚠️ DOM extraction found 0 Pinterest pins. Trying page source fallback...")
        try:
            content = await page.content()
            # Match www.pinterest.com or country subdomains like za.pinterest.com, in.pinterest.com
            pin_urls = re.findall(r'https://(?:[a-z0-9-]+\.)?pinterest\.com/pin/(\d+)', content)
            # Also check for relative /pin/ paths
            pin_urls += re.findall(r'/pin/(\d+)', content)
            pin_ids_seen = set()
            for pin_id in pin_urls:
                if pin_id not in pin_ids_seen and len(pins) < max_posts:
                    pin_ids_seen.add(pin_id)
                    pins.append({
                        "url": f"https://in.pinterest.com/pin/{pin_id}/",
                        "thumbnail": None,
                        "caption": None,
                        "is_video": False,
                    })
            logger.info(f"📋 Page source fallback found {len(pins)} pin URLs")
        except Exception as e:
            logger.error(f"Page source fallback failed: {e}")

    # Scroll to load more pins
    last_count = 0
    for scroll_i in range(max(5, max_posts // 4)):
        new_posts = _pins_to_posts(pins, seen_urls, posts, max_posts)
        posts.extend(new_posts)

        logger.info(f"Scroll {scroll_i + 1}: found {len(posts)} pins so far")

        if len(posts) >= max_posts:
            break

        if len(posts) == last_count and scroll_i > 2:
            logger.info("No new pins found after scrolling, stopping")
            break

        last_count = len(posts)

        # Scroll down
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2500)
        pins = await _extract_pins_from_page(page)

    await save_debug_screenshot(page, "pinterest_done")
    return posts[:max_posts]


async def _dismiss_login_modal(page: Page) -> None:
    """Try to dismiss Pinterest's login modal if present."""
    try:
        login_modal = await page.query_selector('[data-test-id="sidebarLogin"], [id="loginDialog"]')
        if login_modal:
            close_btn = await page.query_selector('[data-test-id="closeup-close-button"], button[aria-label="Close"]')
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(1000)
            logger.info("Dismissed Pinterest login modal")
    except Exception:
        pass


async def _extract_pins_from_page(page: Page) -> list[dict]:
    """Extract pin data from the current page DOM, filtering out board covers, profile headers, and suggested pins."""
    try:
        return await page.evaluate("""
            () => {
                const pins = [];
                const seenHrefs = new Set();
                
                // Pinterest pin links
                const links = document.querySelectorAll('a[href*="/pin/"]');
                
                for (const link of links) {
                    const href = link.href;
                    if (!href || !href.includes('/pin/')) continue;
                    
                    // Extract pin ID for deduplication
                    const pinMatch = href.match(/\\/pin\\/(\\d+)/);
                    if (!pinMatch) continue;
                    const pinId = pinMatch[1];
                    if (seenHrefs.has(pinId)) continue;
                    
                    // ── Filter out board cover images ──
                    // Board covers are inside elements with board-related attributes
                    const isBoardCover = link.closest(
                        '[data-test-id="board-cover"], ' +
                        '[data-test-id="board-card"], ' +
                        '[data-test-id="boardCard"], ' +
                        '[class*="boardCover"], ' +
                        '[class*="BoardCover"], ' +
                        '[class*="board-cover"], ' +
                        '[class*="boardRepTitle"], ' +
                        '[class*="BoardRep"]'
                    );
                    if (isBoardCover) continue;
                    
                    // ── Filter out profile header / avatar area ──
                    const isProfileHeader = link.closest(
                        '[data-test-id="profile-header"], ' +
                        '[data-test-id="profileHeader"], ' +
                        '[class*="profileHeader"], ' +
                        '[class*="ProfileHeader"], ' +
                        '[class*="userProfileHeader"], ' +
                        'header'
                    );
                    if (isProfileHeader) continue;
                    
                    // ── Filter out suggested / related / "More like this" sections ──
                    const isSuggested = link.closest(
                        '[data-test-id="related-pins"], ' +
                        '[data-test-id="moreLikeThis"], ' +
                        '[class*="RelatedPins"], ' +
                        '[class*="relatedPins"]'
                    );
                    if (isSuggested) continue;
                    
                    // ── Skip tiny pin thumbnails (icons, avatars) ──
                    const rect = link.getBoundingClientRect();
                    if (rect.width > 0 && rect.width < 50) continue;
                    if (rect.height > 0 && rect.height < 50) continue;
                    
                    // ── Skip pins in navigation/sidebar areas ──
                    const isNav = link.closest('nav, [role="navigation"], [data-test-id="sidebar"]');
                    if (isNav) continue;
                    
                    seenHrefs.add(pinId);
                    
                    // Get image
                    const img = link.querySelector('img');
                    const thumbnail = img ? (img.src || img.dataset.src) : null;
                    
                    // Get alt text as caption
                    const caption = img ? img.alt : null;
                    
                    // Check if it's a video pin (reel)
                    const text = link.innerText || '';
                    const hasDuration = !!text.match(/\\d+:\\d+/);
                    const isVideoSrc = thumbnail ? (thumbnail.includes('/videos/') || thumbnail.includes('video')) : false;
                    const isVideo = hasDuration || isVideoSrc;
                    
                    pins.push({
                        url: href,
                        thumbnail: thumbnail,
                        caption: caption,
                        is_video: isVideo
                    });
                }
                
                return pins;
            }
        """)
    except Exception as e:
        logger.warning(f"Pin extraction error: {e}")
        return []


def _pins_to_posts(
    pins: list[dict],
    seen_urls: set,
    current_posts: list[PostItem],
    max_posts: int
) -> list[PostItem]:
    """Convert raw pin dicts to PostItem objects, deduplicating."""
    new_posts = []

    for pin in pins:
        if len(current_posts) + len(new_posts) >= max_posts:
            break

        url = pin.get("url", "")
        if not url:
            continue

        # Must look like a real pin URL /pin/DIGITS/
        pin_match = re.search(r"/pin/(\d+)", url)
        if not pin_match:
            continue

        pin_id = pin_match.group(1)
        clean_url = f"https://in.pinterest.com/pin/{pin_id}/"

        if clean_url in seen_urls or url in seen_urls:
            continue

        seen_urls.add(url)
        seen_urls.add(clean_url)

        caption = pin.get("caption")
        if caption and (caption.lower() == "pin image" or len(caption) < 3):
            caption = None

        thumbnail = pin.get("thumbnail")
        # Filter out tiny placeholder images
        if thumbnail and ("placeholder" in thumbnail or "icon" in thumbnail.lower()):
            thumbnail = None

        is_video = pin.get("is_video", False)
        post_type = "reel" if is_video else "post"

        new_posts.append(PostItem(
            post_url=clean_url,
            caption=caption,
            thumbnail_url=thumbnail,
            posted_at=None,  # Pinterest doesn't show dates in pin listings
            likes=None,
            platform="pinterest",
            type=post_type,
        ))
        logger.debug(f"  ✓ Pinterest pin: {clean_url}")

    return new_posts


async def scrape_pinterest(url: str, max_posts: int = 20) -> ScrapeResponse:
    """Scrape latest pins from a Pinterest public board or profile."""
    url = normalize_pinterest_url(url)
    posts: list[PostItem] = []
    error_msg: Optional[str] = None

    try:
        posts = await run_playwright_scrape(
            platform="pinterest",
            scrape_fn=lambda page: _scrape_pinterest_page(page, url, max_posts),
        )
    except ValueError:
        raise
    except Exception as e:
        logger.exception(f"Pinterest scraping failed: {e}")
        if not posts:
            raise RuntimeError(f"Pinterest scraping failed: {e}")
        error_msg = str(e)

    return ScrapeResponse(
        platform="pinterest",
        profile_url=url,
        posts_found=len(posts),
        posts=posts,
        scrape_status="success" if not error_msg else "partial",
        message=error_msg,
    )
