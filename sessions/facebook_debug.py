import asyncio
import logging
import re
from playwright.async_api import async_playwright
from app.utils.session_manager import load_cookies

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("facebook_debug")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        
        cookies = load_cookies("facebook")
        if cookies:
            await context.add_cookies(cookies)
            
        page = await context.new_page()
        url = "https://www.facebook.com/Mahavirnxofficialpage"
        print(f"Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(6000)
        
        await page.screenshot(path="debug_screenshots/mahavir_fb_loaded.png")
        
        # Print page title and current URL
        print(f"Loaded title: {await page.title()}")
        print(f"Loaded URL: {page.url}")
        
        # Get all href links
        links_data = await page.evaluate("""
            () => {
                const results = [];
                const feedContainer = document.querySelector('div[role="feed"], div[data-pagelet="ProfileTimeline"], [data-pagelet="ProfileFeed"]');
                const root = feedContainer || document;
                const elements = Array.from(root.querySelectorAll('a[href]'));
                for (let el of elements) {
                    const rect = el.getBoundingClientRect();
                    results.push({
                        href: el.href,
                        text: el.innerText || '',
                        y: rect.top + window.scrollY
                    });
                }
                return results;
            }
        """)
        
        print(f"Total links: {len(links_data)}")
        
        post_patterns = [
            r"https://(?:[a-zA-Z0-9-]+\.)?facebook\.com/[^/]+/posts/[^\s\"'?]+",
            r"https://(?:[a-zA-Z0-9-]+\.)?facebook\.com/[^/]+/photos/[^\s\"'?]+",
            r"https://(?:[a-zA-Z0-9-]+\.)?facebook\.com/[^/]+/videos/[^\s\"'?]+",
            r"https://(?:[a-zA-Z0-9-]+\.)?facebook\.com/[^/]+/reel/[^\s\"'?]+",
            r"https://(?:[a-zA-Z0-9-]+\.)?facebook\.com/watch/\?[^\s\"']+",
            r"https://(?:[a-zA-Z0-9-]+\.)?facebook\.com/permalink\.php\?[^\s\"']+",
            r"https://(?:[a-zA-Z0-9-]+\.)?facebook\.com/photo/\?[^\s\"']+",
        ]
        
        matched_posts = []
        for item in links_data:
            link = item["href"]
            is_post = any(re.search(pat, link) for pat in post_patterns)
            if is_post:
                matched_posts.append(item)
                print(f"Matched Link: href={link}, text={repr(item['text'])}, y={item['y']}")
                
        if not matched_posts:
            print("No links matched post patterns. Printing first 20 links:")
            for item in links_data[:20]:
                print(f"  • href={item['href']}, text={repr(item['text'])}, y={item['y']}")
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
