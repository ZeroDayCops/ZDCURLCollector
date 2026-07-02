import asyncio
import sys
import logging

sys.path.append("/home/b1t3x0p/ZeroDayCops/ZDCURLCOLEECTOR")

from app.scrapers.facebook import scrape_facebook

logging.basicConfig(level=logging.INFO)

async def main():
    print("🚀 Running Facebook scrape test for Mahavir NX...")
    try:
        res = await scrape_facebook("https://www.facebook.com/Mahavirnxofficialpage", max_posts=3)
        print("\n--- Scrape Finished ---")
        print("Platform:", res.platform)
        print("Status:", res.scrape_status)
        print("Posts Found:", res.posts_found)
        print("Message:", res.message)
        print("\n--- Posts ---")
        for idx, p in enumerate(res.posts):
            print(f"[{idx}] URL: {p.post_url}")
            print(f"    Type: {p.type}")
            print(f"    Caption: {p.caption!r}")
            print(f"    Date: {p.posted_at}")
    except Exception as e:
        print("❌ Scraper failed:", e)

if __name__ == "__main__":
    asyncio.run(main())
