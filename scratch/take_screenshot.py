import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.scrapers.playwright_base import run_playwright_scrape

async def main():
    url = "https://www.facebook.com/Mahavirnxofficialpage"
    print(f"Loading {url}...")
    
    async def page_fn(page):
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(3000)
        
        popups = [
            '[aria-label="Close"]',
            '[aria-label="Dismiss"]',
            'div[role="dialog"] [aria-label="Close"]',
            'div[role="dialog"] i.x',
            'div[role="dialog"] [role="button"]:has-text("Close")',
            'div[role="dialog"] [role="button"]:has-text("Dismiss")',
            '[role="button"]:has-text("Not Now")',
        ]
        for sel in popups:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    print(f"Dismissing popup: {sel}")
                    await el.click()
                    await page.wait_for_timeout(1000)
            except Exception as e:
                print(f"Failed to click {sel}: {e}")
                
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
        except Exception:
            pass
            
        print("Scrolling PageDown 3 times...")
        for i in range(3):
            await page.keyboard.press("PageDown")
            await page.wait_for_timeout(2000)
            
        await page.screenshot(path="scratch/mahavir_after_dismiss.png")
        print("Screenshot saved to scratch/mahavir_after_dismiss.png")
        
        articles = await page.get_by_role("article").all()
        print(f"Found {len(articles)} articles on the page.")
        
    await run_playwright_scrape("facebook", page_fn)

if __name__ == "__main__":
    asyncio.run(main())
