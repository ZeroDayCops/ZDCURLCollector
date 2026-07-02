import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.scrapers.facebook import scrape_facebook

async def main():
    url = "https://www.facebook.com/Mahavirnxofficialpage"
    print(f"Scraping: {url}...")
    try:
        res = await scrape_facebook(url, max_posts=2)
        print("\n=== SCRAPE RESULT ===")
        print("Status:", res.scrape_status)
        print("Message:", res.message)
        print("Posts Found:", res.posts_found)
        for idx, p in enumerate(res.posts, 1):
            print(f"\nPost #{idx}:")
            print("  URL:", p.post_url)
            print("  Date:", p.posted_at)
            print("  Caption:", p.caption)
    except Exception as e:
        print("❌ Scrape failed with error:", e)

if __name__ == "__main__":
    asyncio.run(main())
