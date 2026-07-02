"""
Login Helper — Manual Browser Login & Cookie Saver

Opens a visible (non-headless) Chromium browser, navigates to a platform's
login page, and waits for you to log in manually. Once detected as logged in,
saves the browser cookies to sessions/<platform>_session.json.

Usage:
    python -m app.tools.login_helper instagram
    python -m app.tools.login_helper facebook
    python -m app.tools.login_helper linkedin
    python -m app.tools.login_helper pinterest
"""

import asyncio
import logging
import sys

from playwright.async_api import async_playwright

from app.utils.session_manager import save_cookies

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Platform login URLs and logged-in detection URLs
PLATFORM_CONFIG = {
    "instagram": {
        "login_url": "https://www.instagram.com/accounts/login/",
        "success_indicators": [
            "instagram.com/",     # redirected to feed or profile
        ],
        "fail_indicators": ["accounts/login", "challenge", "two_factor"],
        "domain": "instagram.com",
    },
    "facebook": {
        "login_url": "https://www.facebook.com/login",
        "success_indicators": [
            "facebook.com/",      # redirected to feed
        ],
        "fail_indicators": ["/login", "checkpoint", "/recover"],
        "domain": "facebook.com",
    },
    "linkedin": {
        "login_url": "https://www.linkedin.com/login",
        "success_indicators": [
            "linkedin.com/feed",
            "linkedin.com/in/",
            "linkedin.com/mynetwork",
        ],
        "fail_indicators": ["login", "authwall", "checkpoint"],
        "domain": "linkedin.com",
    },
    "pinterest": {
        "login_url": "https://www.pinterest.com/login/",
        "success_indicators": [
            "pinterest.com/",     # redirected to home
        ],
        "fail_indicators": ["login"],
        "domain": "pinterest.com",
    },
}


async def run_login(platform: str, profile_name: str = "default") -> None:
    """Launch browser with persistent context, let user login, save profile."""
    config = PLATFORM_CONFIG.get(platform)
    if not config:
        print(f"❌ Unknown platform: '{platform}'")
        print(f"   Supported: {', '.join(PLATFORM_CONFIG.keys())}")
        sys.exit(1)

    from app.utils.session_manager import get_profile_path
    profile_path = get_profile_path(platform, profile_name)

    print(f"\n{'='*60}")
    print(f"  🔐 Login Helper — {platform.upper()} (Profile: '{profile_name}')")
    print(f"{'='*60}")
    print(f"\n  A browser window will open.")
    print(f"  Please log in manually.")
    print(f"  Once logged in, the window will close automatically")
    print(f"  and your session profile will be saved.")
    print(f"  📁 Profile location: {profile_path}\n")

    async with async_playwright() as pw:
        # Launch Chromium using persistent browser profile directory
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=False,  # Visible browser for manual login
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,800",
            ],
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )

        # Mask automation signals
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        pages = context.pages
        page = pages[0] if pages else await context.new_page()

        print(f"  🌐 Opening {config['login_url']}...")
        await page.goto(config["login_url"], wait_until="domcontentloaded")

        # Required auth cookies per platform — login is NOT complete without these
        REQUIRED_COOKIES = {
            "instagram": ["sessionid"],
            "facebook": ["c_user", "xs"],
            "linkedin": ["li_at"],
            "pinterest": ["_pinterest_sess"],
        }
        required = REQUIRED_COOKIES.get(platform, [])

        # Poll until user is logged in — ONLY by checking cookies
        print(f"  ⏳ Waiting for you to complete login...")
        if required:
            print(f"  🍪 Will look for auth cookies: {required}")
        max_wait = 300  # 5 minutes max
        check_interval = 3  # check every 3 seconds

        logged_in = False
        for i in range(max_wait // check_interval):
            await asyncio.sleep(check_interval)

            # Check cookies for required auth cookies
            try:
                cookies = await context.cookies()
                cookie_names = {c["name"] for c in cookies}
            except Exception as e:
                # Context might have been closed by user/closed early
                logger.debug(f"Error checking cookies: {e}")
                break

            if required:
                has_all = all(r in cookie_names for r in required)
                if has_all:
                    print(f"  🔑 Found required cookies: {required}")
                    logged_in = True
                    break
            else:
                # No specific requirement — fall back to URL check
                try:
                    current_url = page.url.lower()
                except Exception:
                    break
                is_on_login = any(ind in current_url for ind in config["fail_indicators"])
                is_on_success = any(ind in current_url for ind in config["success_indicators"])
                if is_on_success and not is_on_login:
                    logged_in = True
                    break

            # Progress indicator every 15 seconds
            if (i + 1) % 5 == 0:
                elapsed = (i + 1) * check_interval
                print(f"  ⏳ Still waiting... ({elapsed}s elapsed, cookies: {sorted(cookie_names)})")

        if logged_in:
            # Wait longer for all cookies to fully settle
            print(f"  ⏳ Waiting 5s for all cookies to settle...")
            await asyncio.sleep(5)
            print(f"\n  ✅ SUCCESS! Profile '{profile_name}' is now fully logged in and saved.")
            print(f"  📁 Location: {profile_path}")
        else:
            print(f"\n  ❌ Login timed out or browser was closed before required cookies were set.")
            print(f"  💡 Tip: Try again and complete the login.")

        await context.close()

    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.tools.login_helper <platform> [--profile <profile_name>]")
        print(f"Supported: {', '.join(PLATFORM_CONFIG.keys())}")
        sys.exit(1)

    platform = sys.argv[1].lower().strip()
    profile_name = "default"
    
    if "--profile" in sys.argv:
        try:
            idx = sys.argv.index("--profile")
            profile_name = sys.argv[idx + 1].strip()
        except IndexError:
            print("❌ Error: --profile requires a name argument.")
            sys.exit(1)

    asyncio.run(run_login(platform, profile_name))


if __name__ == "__main__":
    main()

