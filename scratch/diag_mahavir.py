import asyncio
import sys
import logging
from pathlib import Path

sys.path.append("/home/b1t3x0p/ZeroDayCops/ZDCURLCOLEECTOR")

from app.scrapers.playwright_base import run_playwright_scrape, save_debug_screenshot
from playwright.async_api import Page

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diag_mahavir")

url = "https://www.facebook.com/Mahavirnxofficialpage"

async def scrape_fn(page: Page):
    logger.info(f"Navigating to {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=40000)
    await page.wait_for_timeout(5000)
    
    # Scroll down to load posts
    await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
    await page.wait_for_timeout(3000)
    
    # Save a diagnostic screenshot
    await save_debug_screenshot(page, "diag_mahavir")
    
    # Extract page links and elements
    res = await page.evaluate("""
        () => {
            const elements = Array.from(document.querySelectorAll('a[href]'));
            const info = elements.map(el => {
                let parent = el.parentElement;
                let parentChain = [];
                while (parent && parentChain.length < 5) {
                    let id = parent.id ? '#' + parent.id : '';
                    let cls = parent.className ? '.' + parent.className.split(' ').join('.') : '';
                    let role = parent.getAttribute('role') ? `[role="${parent.getAttribute('role')}"]` : '';
                    parentChain.push(parent.tagName.toLowerCase() + id + cls + role);
                    parent = parent.parentElement;
                }
                return {
                    href: el.href,
                    text: el.innerText ? el.innerText.trim() : "",
                    ariaLabel: el.getAttribute('aria-label'),
                    parents: parentChain
                };
            });
            return info;
        }
    """)
    return res

async def main():
    res = await run_playwright_scrape("facebook", scrape_fn)
    print(f"Total links extracted: {len(res)}")
    print("\n--- Links with parent chains ---")
    for idx, r in enumerate(res):
        # Filter for actual post links or potential post links
        if any(p in r['href'] for p in ['/posts/', '/photos/', '/videos/', '/reel/', 'permalink.php', 'photo/?fbid=']):
            print(f"[{idx}] URL: {r['href']}")
            print(f"    Text: {r['text']!r}")
            print(f"    Aria-Label: {r['ariaLabel']!r}")
            print(f"    Parents: { ' -> '.join(r['parents']) }")

if __name__ == "__main__":
    asyncio.run(main())
