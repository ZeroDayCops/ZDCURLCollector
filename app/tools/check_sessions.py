"""
Session Cookie Checker/Auditor
Checks saved browser sessions for Facebook, LinkedIn, Instagram, and Pinterest.
Validates if critical cookies are present and haven't expired.

Usage:
    python -m app.tools.check_sessions
"""

import sys
from pathlib import Path
from datetime import datetime

from app.utils.session_manager import load_session

platforms = ["instagram", "facebook", "linkedin", "pinterest"]

# Critical cookies defined in app/tools/login_helper.py
REQUIRED_COOKIES = {
    "instagram": ["sessionid"],
    "facebook": ["c_user", "xs"],
    "linkedin": ["li_at"],
    "pinterest": ["_pinterest_sess"],
}

def check_all_sessions():
    print("\n================== Session Cookie Integrity Audit ==================")

    all_healthy = True
    for platform in platforms:
        session = load_session(platform)
        if not session:
            print(f"❌ {platform.upper()}: No session file found.")
            print(f"   💡 Action: Run: python -m app.tools.login_helper {platform}")
            print("-" * 68)
            all_healthy = False
            continue

        cookies = session.get("cookies", [])
        user_agent = session.get("user_agent")

        if not isinstance(cookies, list) or len(cookies) == 0:
            print(f"⚠️ {platform.upper()}: Session file exists but has no valid cookies.")
            print(f"   💡 Action: Run: python -m app.tools.login_helper {platform}")
            print("-" * 68)
            all_healthy = False
            continue

        # Audit cookies
        expired_count = 0
        active_count = 0
        session_only_count = 0
        now = datetime.now().timestamp()

        # Build a lookup for status of cookies
        cookie_status = {}
        for cookie in cookies:
            name = cookie.get("name")
            expires = cookie.get("expires")
            
            is_expired = False
            if expires is not None:
                # -1 or other values can represent session cookies
                if expires == -1:
                    session_only_count += 1
                    active_count += 1
                elif float(expires) < now:
                    expired_count += 1
                    is_expired = True
                else:
                    active_count += 1
            else:
                session_only_count += 1
                active_count += 1

            cookie_status[name] = {
                "value_preview": (cookie.get("value", "")[:15] + "...") if cookie.get("value") else "None",
                "is_expired": is_expired,
                "expires_at": datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M:%S') if (expires and expires != -1) else "Session Only"
            }

        # Verify critical cookies
        required = REQUIRED_COOKIES.get(platform, [])
        missing_required = []
        expired_required = []
        
        for req in required:
            if req not in cookie_status:
                missing_required.append(req)
            elif cookie_status[req]["is_expired"]:
                expired_required.append(req)

        # Status Determination
        if missing_required:
            status = "❌ INVALID (Missing Critical Cookies)"
            all_healthy = False
        elif expired_required:
            status = "⚠️ EXPIRED (Critical Cookies Expired)"
            all_healthy = False
        else:
            status = "✅ HEALTHY"

        print(f"{status} {platform.upper()}")
        if user_agent:
            print(f"   - User Agent: {user_agent}")
        else:
            print(f"   - User Agent: Not set")
        print(f"   - Total Cookies: {len(cookies)} (Active: {active_count}, Session-only: {session_only_count}, Expired: {expired_count})")
        
        if required:
            print(f"   - Critical Cookies:")
            for req in required:
                if req in cookie_status:
                    c_info = cookie_status[req]
                    exp_status = "❌ EXPIRED" if c_info["is_expired"] else "✅ ACTIVE"
                    print(f"     * {req}: {c_info['value_preview']} ({exp_status}, Expires: {c_info['expires_at']})")
                else:
                    print(f"     * {req}: ❌ MISSING")
                    
        if status != "✅ HEALTHY":
            print(f"   💡 Action Required: Regenerate session by running:")
            print(f"      python -m app.tools.login_helper {platform}")
            print(f"      (If on VPS, regenerate locally first and then copy to the server's sessions/ directory)")

        print("-" * 68)

    # ── Persistent Profiles Audit ───────────────────────────────────
    print("\n================== Persistent Browser Profiles Audit ==================")
    from app.utils.session_manager import list_profiles, PROFILES_DIR
    
    found_profiles = False
    for platform in platforms:
        profiles = list_profiles(platform)
        if profiles:
            found_profiles = True
            print(f"✅ {platform.upper()}: Found {len(profiles)} persistent profile(s):")
            for profile in profiles:
                p_path = PROFILES_DIR / platform / profile
                print(f"   * '{profile}' -> {p_path}")
        else:
            print(f"ℹ️ {platform.upper()}: No persistent browser profiles found.")
            
    if not found_profiles:
        print("💡 Tip: You can create persistent profiles using command:\n      python -m app.tools.login_helper <platform> --profile <name>")
    print("====================================================================\n")

    if all_healthy or found_profiles:
        print("🎉 SESSIONS/PROFILES AVAILABLE FOR SCRAPING!")
    else:
        print("⚠️ ACTION REQUIRED: SOME SESSIONS/PROFILES NEED SETUP.")
    print("====================================================================\n")

if __name__ == "__main__":
    check_all_sessions()
