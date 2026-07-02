import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright
from app.utils.session_manager import load_cookies

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        
        # Load standard cookies
        cookies = load_cookies("facebook")
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US"
        )
        if cookies:
            await context.add_cookies(cookies)
            print("Cookies injected successfully.")
            
        page = await context.new_page()
        
        url = "https://mbasic.facebook.com/monotmt"
        print(f"Navigating to: {url}...")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        # Take screenshot of the initial landing page
        await page.screenshot(path="scratch/mbasic_screenshot.png")
        print("Saved screenshot to scratch/mbasic_screenshot.png")
        
        # Save HTML of the initial landing page
        html_content = await page.content()
        with open("scratch/mbasic_page.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("Saved HTML to scratch/mbasic_page.html")
        
        # Let's count some elements
        all_anchors = await page.query_selector_all("a")
        print(f"Total anchors found: {len(all_anchors)}")
        for idx, a in enumerate(all_anchors, 1):
            href = await a.get_attribute("href") or ""
            text = await a.inner_text() or ""
            print(f" Anchor {idx}: text='{text.strip()}' href='{href}'")
            
        # Bypass mobile browser choice page if present
        browser_choice = await page.query_selector('a[href*="action=safari"], a[href*="action=chrome"], a[href*="action=firefox"]')
        if browser_choice:
            from urllib.parse import urljoin
            href = await browser_choice.get_attribute("href") or ""
            bypass_url = urljoin("https://mbasic.facebook.com", href)
            print(f"Found mobile browser choice page. Attempting direct navigation to bypass URL: {bypass_url}")
            try:
                await page.goto(bypass_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(4000)
            except Exception as e:
                print(f"Bypass navigation failed/timed out as expected (store redirect): {e}")
                
        print("Current URL:", page.url)
        print("Page Title:", await page.title())
        
        # Take screenshot after bypass attempt
        await page.screenshot(path="scratch/mbasic_after_bypass.png")
        print("Saved screenshot to scratch/mbasic_screenshot.png")
        
        # Save HTML
        html_content = await page.content()
        with open("scratch/mbasic_page.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("Saved HTML to scratch/mbasic_page.html")
        
        # Let's count some elements
        all_anchors = await page.query_selector_all("a")
        print(f"Total anchors found: {len(all_anchors)}")
        
        # Print first 20 anchor hrefs and texts
        print("\nFirst 20 anchors:")
        for idx, a in enumerate(all_anchors[:20], 1):
            href = await a.get_attribute("href") or ""
            text = await a.inner_text() or ""
            print(f" {idx}. text='{text.strip()}' href='{href}'")
            
        await page.close()
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
