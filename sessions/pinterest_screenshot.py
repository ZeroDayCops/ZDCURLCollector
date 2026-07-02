import asyncio
import logging
from playwright.async_api import async_playwright
from app.utils.session_manager import load_cookies

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pinterest_screenshot")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        
        # Load cookies
        cookies = load_cookies("pinterest")
        if cookies:
            await context.add_cookies(cookies)
            
        page = await context.new_page()
        
        # Try _created/
        url1 = "https://www.pinterest.com/mahavir_nx/_created/"
        print(f"Navigating to {url1}")
        try:
            await page.goto(url1, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            await page.screenshot(path="debug_screenshots/mahavir_created.png")
            pins1 = await page.evaluate('Array.from(document.querySelectorAll("a[href*=\'/pin/\']")).map(a => a.href)')
            print(f"_created pins count: {len(pins1)}")
        except Exception as e:
            print(f"Failed to load _created: {e}")
            
        # Try base URL
        url2 = "https://www.pinterest.com/mahavir_nx/"
        print(f"Navigating to {url2}")
        try:
            await page.goto(url2, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)
            await page.screenshot(path="debug_screenshots/mahavir_base.png")
            pins2 = await page.evaluate('Array.from(document.querySelectorAll("a[href*=\'/pin/\']")).map(a => a.href)')
            print(f"base pins count: {len(pins2)}")
        except Exception as e:
            print(f"Failed to load base URL: {e}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
