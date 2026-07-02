import asyncio
import logging
from playwright.async_api import async_playwright
from app.utils.session_manager import load_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("print_fb_links")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # Load cookies
        cookies = load_session("facebook")
        if cookies:
            await context.add_cookies(cookies)
            
        page = await context.new_page()
        url = "https://www.facebook.com/trendsofindiapvtltd"
        print(f"Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        
        links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
        """)
        
        print(f"Total links found: {len(links)}")
        for i, link in enumerate(links):
            if "facebook.com" in link:
                print(f"Link {i}: {link}")
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
