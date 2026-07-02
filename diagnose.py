"""
Diagnostic script — tests each platform scraper individually.
Run: venv/bin/python diagnose.py
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("diagnose")

# ── Platform Detection Test ──────────────────────────────────
def test_platform_detection():
    from app.utils.platform_detector import detect_platform

    test_urls = {
        "https://www.youtube.com/@TRENDSOFINDIAPVTLTD": "youtube",
        "https://www.facebook.com/zuck": "facebook",
        "https://facebook.com/zuck": "facebook",
        "https://www.linkedin.com/in/williamhgates/": "linkedin",
        "https://www.linkedin.com/company/google/": "linkedin",
        "https://www.instagram.com/abhivadan.store/": "instagram",
        "https://www.pinterest.com/pinterest/": "pinterest",
        "https://in.pinterest.com/username/": "pinterest",
    }

    print("\n" + "=" * 60)
    print("  🔍 PHASE 1: Platform Detection Test")
    print("=" * 60)

    all_pass = True
    for url, expected in test_urls.items():
        result = detect_platform(url)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_pass = False
        print(f"  {status} {url[:50]:50s} → {result or 'None':12s} (expected: {expected})")

    return all_pass


# ── Session Cookie Validation ────────────────────────────────
def test_session_cookies():
    print("\n" + "=" * 60)
    print("  🍪 PHASE 2: Session Cookie Validation")
    print("=" * 60)

    # Critical auth cookies per platform
    REQUIRED_AUTH = {
        "instagram": ["sessionid", "ds_user_id"],
        "facebook": ["c_user", "xs"],
        "linkedin": ["li_at"],
        "pinterest": [],  # usually not needed
    }

    sessions_dir = Path("sessions")
    issues = []

    for platform, required in REQUIRED_AUTH.items():
        path = sessions_dir / f"{platform}_session.json"
        if not path.exists():
            print(f"  ❌ {platform.upper():12s} → Session file MISSING: {path}")
            if required:
                issues.append(f"{platform}: no session file")
            continue

        with open(path) as f:
            data = json.load(f)
        
        cookies = data.get("cookies", []) if isinstance(data, dict) else data
        names = {c["name"] for c in cookies}
        missing = [r for r in required if r not in names]

        if missing:
            print(f"  ❌ {platform.upper(
                
            ):12s} → {len(cookies)} cookies, MISSING AUTH: {missing}")
            print(f"     Present: {sorted(names)}")
            issues.append(f"{platform}: missing {missing}")
        else:
            present_auth = [n for n in names if n in (set(required) | {"sessionid", "ds_user_id", "c_user", "xs", "li_at", "JSESSIONID", "_pinterest_sess"})]
            print(f"  ✅ {platform.upper():12s} → {len(cookies)} cookies, auth: {present_auth}")

    if issues:
        print(f"\n  ⚠️  FIX REQUIRED: Re-login to refresh cookies:")
        for issue in issues:
            platform = issue.split(":")[0]
            print(f"     python -m app.tools.login_helper {platform}")

    return len(issues) == 0


# ── Dedup Tracker Inspection ─────────────────────────────────
def test_dedup():
    print("\n" + "=" * 60)
    print("  📋 PHASE 3: Dedup Tracker State")
    print("=" * 60)

    path = Path("data/sent_posts.json")
    if not path.exists():
        print("  ℹ️  No sent_posts.json found (clean state)")
        return True

    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ❌ Failed to parse {path}: {e}")
        return False

    history = []
    if isinstance(data, list):
        for url in data:
            history.append((url, "Unknown"))
    elif isinstance(data, dict):
        if "history" in data:
            for entry in data["history"]:
                history.append((entry.get("url", ""), entry.get("sent_at", "Unknown")))
        else:
            for url, ts in data.items():
                from datetime import datetime
                try:
                    dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    dt = str(ts)
                history.append((url, dt))

    print(f"  📊 {len(history)} URLs tracked as already-sent:")
    for url, dt in history:
        # Detect platform from URL
        platform = "unknown"
        if "youtube" in url: platform = "youtube"
        elif "instagram" in url: platform = "instagram"
        elif "facebook" in url: platform = "facebook"
        elif "linkedin" in url: platform = "linkedin"
        elif "pinterest" in url: platform = "pinterest"
        print(f"     [{platform:10s}] {url[:60]:60s} (sent {dt})")

    if history:
        print(f"\n  ⚠️  These URLs will be SKIPPED on next scrape if sent <30 min ago.")
        print(f"     To reset: rm data/sent_posts.json")

    return True



# ── YouTube Quick Test ───────────────────────────────────────
def test_youtube():
    print("\n" + "=" * 60)
    print("  ▶️  PHASE 4A: YouTube Scraper Test")
    print("=" * 60)

    try:
        from app.scrapers.youtube import scrape_youtube
        result = scrape_youtube("https://www.youtube.com/@TRENDSOFINDIAPVTLTD", max_posts=1)
        print(f"  Status: {result.scrape_status}")
        print(f"  Posts found: {result.posts_found}")
        for p in result.posts:
            print(f"  → {p.post_url} (type: {p.type})")
        return result.posts_found > 0
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False


# ── Facebook Quick Test ──────────────────────────────────────
async def test_facebook():
    print("\n" + "=" * 60)
    print("  📘 PHASE 4B: Facebook Scraper Test")
    print("=" * 60)

    try:
        from app.scrapers.facebook import scrape_facebook
        result = await scrape_facebook("https://www.facebook.com/monotmt", max_posts=1)
        print(f"  Status: {result.scrape_status}")
        print(f"  Posts found: {result.posts_found}")
        if result.message:
            print(f"  Message: {result.message}")
        for p in result.posts:
            print(f"  → {p.post_url} (type: {p.type})")
        return result.posts_found > 0
    except ValueError as e:
        print(f"  ❌ AUTH ISSUE: {e}")
        print(f"     FIX: python -m app.tools.login_helper facebook")
        return False
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False


# ── LinkedIn Quick Test ──────────────────────────────────────
async def test_linkedin():
    print("\n" + "=" * 60)
    print("  💼 PHASE 4C: LinkedIn Scraper Test")
    print("=" * 60)

    try:
        from app.scrapers.linkedin import scrape_linkedin
        result = await scrape_linkedin("https://www.linkedin.com/company/google/", max_posts=1)
        print(f"  Status: {result.scrape_status}")
        print(f"  Posts found: {result.posts_found}")
        if result.message:
            print(f"  Message: {result.message}")
        for p in result.posts:
            print(f"  → {p.post_url} (type: {p.type})")
        return result.posts_found > 0
    except ValueError as e:
        print(f"  ❌ AUTH ISSUE: {e}")
        print(f"     FIX: python -m app.tools.login_helper linkedin")
        return False
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────
async def main():
    print("\n🔬 ZDCURLCOLEECTOR — Full Diagnostic Suite")
    print("=" * 60)

    # Phase 1: Platform detection
    detection_ok = test_platform_detection()

    # Phase 2: Session cookies
    cookies_ok = test_session_cookies()

    # Phase 3: Dedup state
    dedup_ok = test_dedup()

    # Phase 4: Individual scraper tests
    yt_ok = test_youtube()
    fb_ok = await test_facebook()
    li_ok = await test_linkedin()

    # Summary
    print("\n" + "=" * 60)
    print("  📊 DIAGNOSTIC SUMMARY")
    print("=" * 60)
    print(f"  {'✅' if detection_ok else '❌'} Platform Detection: {'ALL PASS' if detection_ok else 'ISSUES FOUND'}")
    print(f"  {'✅' if cookies_ok else '❌'} Session Cookies: {'ALL VALID' if cookies_ok else 'NEEDS RE-LOGIN'}")
    print(f"  {'✅' if dedup_ok else '❌'} Dedup Tracker: {'OK' if dedup_ok else 'ISSUES'}")
    print(f"  {'✅' if yt_ok else '❌'} YouTube Scraper: {'WORKING' if yt_ok else 'BROKEN'}")
    print(f"  {'✅' if fb_ok else '❌'} Facebook Scraper: {'WORKING' if fb_ok else 'BROKEN — re-login needed'}")
    print(f"  {'✅' if li_ok else '❌'} LinkedIn Scraper: {'WORKING' if li_ok else 'BROKEN — check cookies/auth'}")
    print()

    if not cookies_ok:
        print("  🔧 PRIORITY FIX: Run these commands to refresh cookies:")
        print("     python -m app.tools.login_helper facebook")
        print("     python -m app.tools.login_helper linkedin")
        print()


if __name__ == "__main__":
    asyncio.run(main())
