import asyncio
import sys
import logging
from pathlib import Path

sys.path.append("/home/b1t3x0p/ZeroDayCops/ZDCURLCOLEECTOR")

from app.scrapers.playwright_base import run_playwright_scrape
from playwright.async_api import Page

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fb_dom_details")

url = "https://www.facebook.com/Mahavirnxofficialpage"

async def scrape_fn(page: Page):
    logger.info(f"Navigating to {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=40000)
    await page.wait_for_timeout(5000)
    
    # Scroll down once to trigger loading of posts
    await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
    await page.wait_for_timeout(3000)
    
    res = await page.evaluate("""
        () => {
            const articles = Array.from(document.querySelectorAll('[role="article"]'));
            const articleInfo = articles.map((a, i) => {
                const hrefs = Array.from(a.querySelectorAll('a[href]')).map(el => el.href);
                return {
                    index: i,
                    tagName: a.tagName,
                    className: a.className,
                    textSnippet: a.innerText ? a.innerText.slice(0, 100).replace(/\n/g, ' ') : "",
                    hrefs: hrefs
                };
            });
            
            // Also find any divs that look like posts but might not have role="article"
            const divs = Array.from(document.querySelectorAll('div'));
            const potentialPosts = divs.filter(d => d.innerText && (d.innerText.includes('Bhagalpur') || d.innerText.includes('13 June'))).map(d => {
                return {
                    tagName: d.tagName,
                    className: d.className,
                    role: d.getAttribute('role'),
                    textSnippet: d.innerText.slice(0, 100).replace(/\n/g, ' ')
                };
            }).slice(0, 10);
            
            return {
                articleCount: articles.length,
                articles: articleInfo,
                potentialPosts: potentialPosts
            };
        }
    """)
    return res

async def main():
    res = await run_playwright_scrape("facebook", scrape_fn)
    print("Article Count:", res["articleCount"])
    print("\n--- Articles Found ---")
    for a in res["articles"]:
        print(f"[{a['index']}] Tag: {a['tagName']}, Class: {a['className']}")
        print(f"    Text: {a['textSnippet']!r}")
        print(f"    URLs: {a['hrefs']}")
        
    print("\n--- Potential Post Elements (by text search) ---")
    for p in res["potentialPosts"]:
        print(f"Tag: {p['tagName']}, Class: {p['className']}, Role: {p['role']}")
        print(f"    Text: {p['textSnippet']!r}")

if __name__ == "__main__":
    asyncio.run(main())
