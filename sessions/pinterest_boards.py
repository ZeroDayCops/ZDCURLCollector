import asyncio
import logging
from playwright.async_api import async_playwright
from app.utils.session_manager import load_cookies

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pinterest_boards")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        
        cookies = load_cookies("pinterest")
        if cookies:
            await context.add_cookies(cookies)
            
        page = await context.new_page()
        url = "https://www.pinterest.com/mahavir_nx/"
        print(f"Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        
        # Get all links and their inner text or child structure
        links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a')).map(a => ({
                href: a.href,
                text: a.innerText || ''
            }))
        """)
        
        print(f"Total links: {len(links)}")
        for i, link in enumerate(links):
            if "mahavir_nx" in link["href"]:
                print(f"Link {i}: href={link['href']}, text={repr(link['text'])}")
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
