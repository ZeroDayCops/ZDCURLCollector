import asyncio
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[4] / "Desktop" / "ZDCURLCOLEECTORFINAL"))

from app.utils.session_manager import list_profiles, get_profile_path

REQUIRED_COOKIES = {
    "instagram": ["sessionid"],
    "facebook": ["c_user", "xs"],
}

async def audit_profile(platform: str, profile_name: str) -> dict:
    profile_path = get_profile_path(platform, profile_name)
    required = REQUIRED_COOKIES.get(platform, [])
    
    async with async_playwright() as pw:
        try:
            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            cookies = await context.cookies()
            try:
                await context.close()
            except Exception:
                pass
            
            cookie_names = {c["name"] for c in cookies}
            missing = [r for r in required if r not in cookie_names]
            
            if missing:
                return {
                    "status": "❌ LOGGED OUT",
                    "reason": f"Missing critical cookies: {missing}",
                    "cookies_present": sorted(list(cookie_names))
                }
            else:
                # Find some values to preview
                details = {}
                for r in required:
                    for c in cookies:
                        if c["name"] == r:
                            details[r] = c["value"][:10] + "..."
                return {
                    "status": "✅ LOGGED IN",
                    "details": details,
                    "total_cookies": len(cookies)
                }
        except Exception as e:
            return {
                "status": "❌ ERROR",
                "reason": str(e)
            }

async def main():
    print("\n====================================================================")
    print(" 🕵️‍♂️  PERSISTENT PROFILES LOGIN AUDIT TOOL")
    print("====================================================================\n")
    
    platforms = ["instagram", "facebook"]
    for platform in platforms:
        profiles = list_profiles(platform)
        print(f"📁 Platform: {platform.upper()}")
        if not profiles:
            print("   (No persistent profiles configured)\n")
            continue
            
        for profile in sorted(profiles):
            print(f"   ⏳ Auditing '{profile}'... ", end="", flush=True)
            res = await audit_profile(platform, profile)
            print(res["status"])
            if res["status"] != "✅ LOGGED IN":
                print(f"      💡 Reason: {res.get('reason')}")
            else:
                cookie_str = ", ".join([f"{k}={v}" for k, v in res.get("details", {}).items()])
                print(f"      🔑 Session active: {cookie_str} (Total cookies: {res.get('total_cookies')})")
        print()
    print("====================================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
