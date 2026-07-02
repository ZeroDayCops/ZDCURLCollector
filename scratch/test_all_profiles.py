import asyncio
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import app.utils.session_manager
from app.scrapers.facebook import scrape_facebook

logging.basicConfig(level=logging.INFO)

async def test_profile(profile_name: str):
    print(f"\n=========================================")
    print(f"👤 TESTING WITH PROFILE: {profile_name}")
    print(f"=========================================")
    
    # Mock get_next_profile to return the specific profile name
    app.utils.session_manager.get_next_profile = lambda platform: profile_name
    
    try:
        res = await scrape_facebook("https://www.facebook.com/Mahavirnxofficialpage", max_posts=2)
        print(f"Profile '{profile_name}' Result: {res.scrape_status} | Posts Found: {res.posts_found}")
        for p in res.posts:
            print(f"  → {p.post_url} ({p.posted_at})")
    except Exception as e:
        print(f"❌ Profile '{profile_name}' Failed: {e}")

async def main():
    profiles = ["acc_2", "acc_3", "acc_4", "acc_5", "acc_6", "acc_7", "default"]
    for p in profiles:
        await test_profile(p)
        # Short cooldown sleep between profiles
        await asyncio.sleep(2.0)

if __name__ == "__main__":
    asyncio.run(main())
