"""
Base Playwright scraper with:
- Cookie-based session loading
- Anti-bot detection evasion (stealth headers, viewport, user-agent)
- Retry logic with user-agent rotation
- Platform-aware proxy strategy (direct-first vs proxy-first)
- Screenshot-on-error debugging
"""

import asyncio
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional, Callable, Any

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from app.utils.session_manager import load_cookies

logger = logging.getLogger(__name__)

DEBUG_SCREENSHOTS = os.getenv("DEBUG_SCREENSHOTS", "false").lower() == "true"
SCREENSHOTS_DIR = Path("./debug_screenshots")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
]

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 3  # seconds (reduced from 5 to speed up retries)

# ── Platform-aware proxy strategy ─────────────────────────────
# "never"        = always use direct connection (for platforms that block proxies)
# "direct_first" = attempt 1 uses NO proxy, retries use proxy
# "proxy_first"  = attempt 1 uses proxy, last retry uses direct
PLATFORM_PROXY_STRATEGY = {
    "facebook":  "never",          # Facebook blocks proxies instantly, always use direct
    "linkedin":  "never",          # LinkedIn needs session cookies + stable direct connection
    "instagram": "proxy_first",    # Instagram often blocks direct
    "pinterest": "proxy_first",    # in.pinterest.com is blocked direct
    "youtube":   "never",          # YouTube is public, direct is fast and stable
}


async def create_stealth_context(
    browser: Browser,
    platform: str,
    user_agent: Optional[str] = None,
) -> BrowserContext:
    """
    Create a Playwright browser context with:
    - Realistic user agent and viewport
    - Cookies loaded from saved session
    - Extra HTTP headers to appear human
    """
    ua = user_agent or random.choice(USER_AGENTS)
    viewport = {"width": 1366, "height": 768}

    context = await browser.new_context(
        user_agent=ua,
        viewport=viewport,
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={
            "Accept-Language": "en-US,en;q=0.9",
        },
        java_script_enabled=True,
    )

    # Grant clipboard permissions for copy operations (e.g. copy LinkedIn post link)
    try:
        await context.grant_permissions(["clipboard-read", "clipboard-write"])
    except Exception as e:
        logger.debug(f"Could not grant clipboard permissions: {e}")

    # Load saved cookies if available
    cookies = load_cookies(platform)
    if cookies:
        await context.add_cookies(cookies)
        logger.info(f"✅ Injected {len(cookies)} saved cookies for {platform}")
    else:
        logger.warning(f"⚠️  No saved cookies for {platform}. You may need to run the login helper first!")
        logger.warning(f"    Run: python -m app.tools.login_helper {platform}")

    # Mask automation signals
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)

    return context


async def simulate_mouse_movement(page: Page) -> None:
    """Move the mouse pointer to random coordinates to simulate a human user."""
    try:
        width, height = 1366, 768
        x, y = random.randint(100, 500), random.randint(100, 500)
        await page.mouse.move(x, y)
        
        steps = random.randint(3, 7)
        for _ in range(steps):
            target_x = random.randint(100, width - 100)
            target_y = random.randint(100, height - 100)
            
            # Smooth interpolation steps
            current_steps = random.randint(5, 15)
            for step in range(1, current_steps + 1):
                curr_x = x + (target_x - x) * (step / current_steps)
                curr_y = y + (target_y - y) * (step / current_steps)
                await page.mouse.move(curr_x, curr_y)
                await asyncio.sleep(random.uniform(0.01, 0.03))
                
            x, y = target_x, target_y
            await asyncio.sleep(random.uniform(0.2, 0.8))
    except Exception as e:
        logger.debug(f"Mouse movement simulation failed: {e}")


async def scroll_and_collect(
    page: Page,
    scroll_pause: float = 2.0,
    max_scrolls: int = 10,
    stop_condition: Optional[Callable[[Page], bool]] = None,
) -> None:
    """
    Scroll the page gradually with human-like jitter, varying speed, and occasional backtracking.
    """
    last_height = await page.evaluate("document.body.scrollHeight")
    
    for i in range(max_scrolls):
        # Human simulation: Move mouse occasionally
        if random.random() < 0.3:
            await simulate_mouse_movement(page)
            
        # Scroll down in smaller random chunks
        current_y = await page.evaluate("window.scrollY")
        target_y = current_y + random.randint(600, 900)
        
        # Scroll down gradually
        steps = random.randint(5, 10)
        for step in range(1, steps + 1):
            y_step = current_y + (target_y - current_y) * (step / steps)
            await page.evaluate(f"window.scrollTo(0, {y_step})")
            await asyncio.sleep(random.uniform(0.05, 0.15))
            
        # Jitter: Scroll back up slightly occasionally
        if random.random() < 0.2:
            back_y = max(0, target_y - random.randint(100, 200))
            await page.evaluate(f"window.scrollTo(0, {back_y})")
            await asyncio.sleep(random.uniform(0.2, 0.5))
            await page.evaluate(f"window.scrollTo(0, {target_y})")
            
        # Randomize the scroll pause length
        actual_pause = scroll_pause * random.uniform(0.8, 1.4)
        await asyncio.sleep(actual_pause)

        new_height = await page.evaluate("document.body.scrollHeight")
        logger.debug(f"Scroll {i+1}/{max_scrolls}: height {last_height} → {new_height}")

        if stop_condition and stop_condition(page):
            logger.info("Stop condition met, ending scroll")
            break

        # Check if we have hit bottom
        current_y_after = await page.evaluate("window.scrollY + window.innerHeight")
        if new_height == last_height and current_y_after >= new_height - 50:
            logger.info("Reached bottom, no more content to scroll")
            break

        last_height = new_height



async def save_debug_screenshot(page: Page, name: str) -> None:
    if not DEBUG_SCREENSHOTS:
        return
    try:
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOTS_DIR / f"{name}_{int(time.time())}.png"
        await page.screenshot(path=str(path), full_page=False)
        logger.info(f"📸 Debug screenshot: {path}")
    except Exception as e:
        logger.debug(f"Screenshot failed: {e}")


def _should_use_proxy(platform: str, attempt: int, max_retries: int) -> bool:
    """Decide whether to use a proxy for this platform + attempt combination."""
    strategy = PLATFORM_PROXY_STRATEGY.get(platform, "proxy_first")

    if strategy == "never":
        return False
    elif strategy == "direct_first":
        # Attempt 1 = direct, attempts 2+ = proxy
        return attempt > 1
    else:
        # proxy_first: attempts 1..(max-1) = proxy, last attempt = direct fallback
        return attempt < max_retries


async def run_playwright_scrape(
    platform: str,
    scrape_fn: Callable[[Page], Any],
    headless: bool = True,
    max_retries: int = MAX_RETRIES,
) -> Any:
    """
    Generic Playwright runner with retry and user-agent rotation.

    Accepts a scrape function that receives a Page.
    Handles browser lifecycle, context creation, retries, and error handling.

    Uses platform-aware proxy strategy:
    - "direct_first" platforms (Facebook, LinkedIn): try direct first, proxy on retries
    - "proxy_first" platforms (Instagram, Pinterest): try proxy first, direct on last retry
    """
    last_error: Optional[Exception] = None
    strategy = PLATFORM_PROXY_STRATEGY.get(platform, "proxy_first")
    from app.utils.session_manager import load_session, list_profiles
    session = load_session(platform)
    saved_ua = session.get("user_agent") if session else None
    
    num_profiles = len(list_profiles(platform))
    actual_retries = max(max_retries, num_profiles) if num_profiles > 0 else max_retries

    for attempt in range(1, actual_retries + 1):
        # Use saved UA if available (avoids session invalidation), else rotate
        ua = saved_ua or USER_AGENTS[(attempt - 1) % len(USER_AGENTS)]
        logger.info(f"🔄 Playwright attempt {attempt}/{actual_retries} for {platform} "
                     f"(strategy: {strategy}, UA: {ua[:40]}...)")

        try:
            async with async_playwright() as pw:
                # Platform-aware proxy decision
                use_proxy = _should_use_proxy(platform, attempt, actual_retries)

                proxy_dict = None
                if use_proxy:
                    from app.utils.proxy_manager import get_next_proxy
                    proxy_server = get_next_proxy()
                    if proxy_server:
                        proxy_dict = {"server": proxy_server}
                        proxy_user = (os.getenv("PLAYWRIGHT_PROXY_USERNAME", "").strip()
                                      or os.getenv("PROXY_USERNAME", "").strip())
                        proxy_pass = (os.getenv("PLAYWRIGHT_PROXY_PASSWORD", "").strip()
                                      or os.getenv("PROXY_PASSWORD", "").strip())
                        if proxy_user:
                            proxy_dict["username"] = proxy_user
                        if proxy_pass:
                            proxy_dict["password"] = proxy_pass
                        logger.info(f"🌐 Using PROXY (Attempt {attempt}): {proxy_server}")
                    else:
                        logger.info(f"🌐 No proxy available, using DIRECT for attempt {attempt}")
                else:
                    logger.info(f"🌐 Using DIRECT connection (Attempt {attempt}) — {strategy} strategy")

                browser = None
                context = None
                page = None
                
                from app.utils.session_manager import has_persistent_profiles, get_next_profile, get_profile_path
                
                if has_persistent_profiles(platform):
                    profile_name = get_next_profile(platform)
                    profile_path = get_profile_path(platform, profile_name)
                    logger.info(f"🚀 Launching persistent browser profile '{profile_name}' for {platform}")
                    
                    context = await pw.chromium.launch_persistent_context(
                        user_data_dir=str(profile_path),
                        headless=headless,
                        proxy=proxy_dict,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-infobars",
                            "--window-size=1366,768",
                        ],
                        user_agent=ua,
                        viewport={"width": 1366, "height": 768},
                        locale="en-US",
                        timezone_id="America/New_York",
                        extra_http_headers={
                            "Accept-Language": "en-US,en;q=0.9",
                        },
                        java_script_enabled=True,
                    )
                    
                    # Mask automation signals
                    await context.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                        window.chrome = { runtime: {} };
                    """)
                    
                    try:
                        await context.grant_permissions(["clipboard-read", "clipboard-write"])
                    except Exception as e:
                        logger.debug(f"Could not grant clipboard permissions: {e}")
                        
                    pages = context.pages
                    page = pages[0] if pages else await context.new_page()
                else:
                    logger.info(f"🚀 No persistent browser profiles found for {platform}. Falling back to flat session cookies.")
                    browser = await pw.chromium.launch(
                        headless=headless,
                        proxy=proxy_dict,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-infobars",
                            "--window-size=1366,768",
                        ],
                    )
                    context = await create_stealth_context(browser, platform, user_agent=ua)
                    page = await context.new_page()

                # Set default navigation/page timeout (60s) to give ample time on proxy/slow networks
                timeout_ms = 60000
                page.set_default_navigation_timeout(timeout_ms)
                page.set_default_timeout(timeout_ms)


                # Human-like delay after opening browser context (hydration wait is handled in platform scrapers)
                initial_delay = random.uniform(1.5, 3.5)
                logger.info(f"⏳ Simulating human startup pause: sleeping {initial_delay:.2f}s...")
                await page.wait_for_timeout(int(initial_delay * 1000))

                # Block heavy assets to speed up page loads over slow proxies
                # NOTE: We keep images for Pinterest (pin links need img elements) only.
                #       Also abort App Store / Play Store / deep links to prevent timeouts.
                async def block_heavy_assets(route):
                    url = route.request.url.lower()
                    
                    # ── Block App Store / Deep Link request ──
                    if (url.startswith("intent://") or 
                        url.startswith("itms-apps://") or 
                        "play.google.com" in url or 
                        "use_store_link=1" in url or
                        "apps.apple.com" in url or
                        "itunes.apple.com" in url):
                        logger.info(f"🚫 Aborting App Store / Deep Link request: {url}")
                        await route.abort()
                        return

                    resource_type = route.request.resource_type
                    if resource_type in ["font", "media"]:
                        await route.abort()
                    elif resource_type == "image":
                        # Block images on all platforms except Pinterest
                        if platform == "pinterest":
                            await route.continue_()
                        else:
                            await route.abort()
                    elif resource_type == "stylesheet":
                        # Block stylesheets except on Pinterest and Facebook (needs CSS for layout)
                        if platform in ["pinterest", "facebook"]:
                            await route.continue_()
                        else:
                            await route.abort()
                    else:
                        await route.continue_()
                await page.route("**/*", block_heavy_assets)

                try:
                    result = await scrape_fn(page)
                    # Human-like delay before closing page to make it look natural
                    final_delay = random.uniform(2.0, 4.0)
                    logger.info(f"⏳ Simulating human read/exit pause: sleeping {final_delay:.2f}s...")
                    await page.wait_for_timeout(int(final_delay * 1000))
                    return result
                except PlaywrightTimeoutError as e:
                    await save_debug_screenshot(page, f"{platform}_timeout_attempt{attempt}")
                    last_error = RuntimeError(f"Page timed out while scraping {platform}: {e}")
                except Exception as e:
                    await save_debug_screenshot(page, f"{platform}_error_attempt{attempt}")
                    last_error = e
                    # Don't retry on ValueError (user-facing errors like "login required")
                    # unless we have multiple persistent profiles to rotate to for this platform
                    from app.utils.session_manager import list_profiles
                    has_multiple_profiles = len(list_profiles(platform)) > 1
                    if isinstance(e, ValueError) and not has_multiple_profiles:
                        raise
                finally:
                    if page:
                        try:
                            await page.close()
                        except Exception:
                            pass
                    if context:
                        try:
                            await context.close()
                        except Exception:
                            pass
                    if browser:
                        try:
                            await browser.close()
                        except Exception:
                            pass

        except ValueError:
            raise
        except Exception as e:
            last_error = e

        # Backoff before next retry
        if attempt < actual_retries:
            from app.utils.session_manager import has_persistent_profiles
            if has_persistent_profiles(platform):
                backoff = random.uniform(1.5, 3.0)
            else:
                backoff = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(f"⏳ Retry backoff: waiting {backoff:.2f}s before attempt {attempt + 1}")
            await asyncio.sleep(backoff)

    # All retries exhausted
    raise RuntimeError(
        f"Playwright scraping failed for {platform} after {actual_retries} attempts: {last_error}"
    )
