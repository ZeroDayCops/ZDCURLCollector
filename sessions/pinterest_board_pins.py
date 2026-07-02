import asyncio
import logging
from playwright.async_api import async_playwright
from app.utils.session_manager import load_cookies

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pinterest_board_pins")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        
        cookies = load_cookies("pinterest")
        if cookies:
            await context.add_cookies(cookies)
            
        page = await context.new_page()
        url = "https://www.pinterest.com/mahavir_nx/kurta/"
        print(f"Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        
        await page.screenshot(path="debug_screenshots/mahavir_board_kurta.png")
        
        pins = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href*="/pin/"]')).map(a => a.href)
        """)
        
        print(f"Total pin links on board: {len(pins)}")
        for i, pin in enumerate(pins[:10]):
            print(f"Pin {i}: {pin}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
