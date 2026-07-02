import asyncio
import time
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Set up logging to print to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("one_by_one_scraper")

# Add the project directory to python path
project_dir = Path(__file__).resolve().parent
sys.path.append(str(project_dir))

from app.telegram_bot.ui_api import parse_txt_file, scrape_single_url, setup_run_logging, teardown_run_logging
from app.telegram_bot.bot import send_brand_message, setup_telegram_log_handler
from app.telegram_bot.dedup import mark_sent, is_new, clear_sent_posts_cache
from app.utils.platform_detector import detect_platform
from app.utils.date_parser import is_recent_post

async def run_one_by_one():
    # Setup Telegram log handler to redirect warnings and errors to admin
    setup_telegram_log_handler()

    # 1. Setup date-wise structured run logging
    handler, log_file, out_filename = setup_run_logging("file")
    
    # 2. Clear sent posts cache for the new scan
    clear_sent_posts_cache()

    try:
        # Verify Telegram channel settings
        channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
        if not channel_id:
            logger.error("❌ TELEGRAM_CHANNEL_ID is not configured in .env!")
            return

        # Check for links.txt
        links_file = project_dir / "links.txt"
        if not links_file.exists():
            logger.error(f"❌ links.txt not found at {links_file}!")
            return

        logger.info(f"📖 Reading links from: {links_file}")
        with open(links_file, "r") as f:
            content = f.read()

        brands = parse_txt_file(content)
        if not brands:
            logger.error("❌ No brands or URLs parsed from links.txt!")
            return

        logger.info(f"📋 Found {len(brands)} brands in links.txt:")
        for brand, urls in brands.items():
            logger.info(f"  • {brand}: {len(urls)} URLs")

        print("\n🚀 Starting Brand-by-Brand scraping and posting...")
        
        total_urls = sum(len(urls) for urls in brands.values())
        processed_count = 0
        start_time = time.time()
        
        shared_by_brand = {}

        for brand_idx, (brand_name, urls) in enumerate(brands.items(), 1):
            logger.info(f"\n==================================================")
            logger.info(f"🏷️  [{brand_idx}/{len(brands)}] Scraping Brand: {brand_name}")
            logger.info(f"==================================================")
            
            all_scrape_responses = []
            results = []
            # Track ALL scraped URLs for output file (not just sent ones)
            all_scraped_by_platform: dict[str, list[str]] = {}

            # Pre-initialize platform lists to ensure they always show up in the output report
            for url in urls:
                plat = detect_platform(url)
                if plat:
                    all_scraped_by_platform[plat] = []
            
            for url_idx, url in enumerate(urls, 1):
                processed_count += 1
                percent = (processed_count / total_urls) * 100
                
                elapsed = time.time() - start_time
                if processed_count > 1:
                    avg_time = elapsed / (processed_count - 1)
                    remaining_urls = total_urls - processed_count + 1
                    eta_sec = avg_time * remaining_urls
                    mins = int(eta_sec // 60)
                    secs = int(eta_sec % 60)
                    eta_str = f"~{mins}m {secs}s"
                else:
                    eta_str = "Estimating..."
                    
                logger.info(f"🔍 [{processed_count}/{total_urls}] ({percent:.1f}%) | ETA: {eta_str} | Scraping: {url} ...")
                
                # Scrape the profile
                try:
                    result = await scrape_single_url(url, max_posts=1)
                except Exception as e:
                    logger.exception(f"❌ Unexpected error scraping {url}: {e}")
                    result = {
                        "url": url,
                        "status": "error",
                        "error": str(e),
                        "posts": [],
                    }
                
                if result.get("status") == "success" and "scrape_response" in result:
                    scrape_resp = result.pop("scrape_response")
                    platform = scrape_resp.platform
                    if platform not in all_scraped_by_platform:
                        all_scraped_by_platform[platform] = []

                    recent_posts = []
                    if scrape_resp.posts:
                        recent_posts = [p for p in scrape_resp.posts if is_recent_post(p.posted_at)]

                    if not recent_posts:
                        scrape_resp.message = "no_recent_posts"
                        scrape_resp.posts = []
                        all_scraped_by_platform[platform].append("⚠️ Not posted from last 4 days")
                        all_scrape_responses.append(scrape_resp)
                        logger.info(f"  ⚠️ SUCCESS but NO posts found in last 4 days for: {url}")
                    else:
                        # Record recent posts in the output tracker (formatted with dates)
                        for p in recent_posts:
                            date_suffix = ""
                            if p.posted_at:
                                date_str = p.posted_at.split(" ")[0].split("T")[0]
                                date_suffix = f" ({date_str})"
                            all_scraped_by_platform[platform].append(f"{p.post_url}{date_suffix}")

                        new_posts = [p for p in recent_posts if is_new(p.post_url)]
                        if new_posts:
                            scrape_resp.posts = new_posts
                            all_scrape_responses.append(scrape_resp)
                            logger.info(f"  ✅ SUCCESS (NEW): Found post -> {scrape_resp.posts[0].post_url}")
                        else:
                            scrape_resp.message = "all_duplicates"
                            scrape_resp.posts = []
                            all_scrape_responses.append(scrape_resp)
                            logger.info("  ⚠️ SUCCESS but posts are duplicates or already sent")
                else:
                    if "scrape_response" in result:
                        result.pop("scrape_response")
                    logger.error(f"  ❌ FAILED: {result.get('error', 'Unknown error')}")
                    # Track failed platforms in output
                    platform = result.get("platform", "unknown")
                    if platform != "unknown":
                        if platform not in all_scraped_by_platform:
                            all_scraped_by_platform[platform] = []
                        all_scraped_by_platform[platform].append("❌ Failed")
                
                results.append(result)
                
                # Sleep between URLs to avoid platform rate-limits (2 seconds)
                sleep_time = 2.0
                logger.info(f"💤 Sleeping for {sleep_time} seconds before next URL...")
                await asyncio.sleep(sleep_time)

            # Collect failed platforms for error reporting in Telegram message
            failed_platforms = [
                r["platform"] for r in results
                if r.get("status") == "error" and r.get("platform", "unknown") != "unknown"
            ]

            # Send brand message if we have any successful posts
            if all_scrape_responses:
                logger.info(f"📤 Sending brand-wise message to Telegram for: {brand_name}")
                success = await send_brand_message(
                    brand_name=brand_name,
                    results=all_scrape_responses,
                    channel_id=channel_id,
                    failed_platforms=failed_platforms,
                )
                if success:
                    logger.info(f"🎉 Successfully posted brand '{brand_name}' to Telegram!")
                    for resp in all_scrape_responses:
                        for post in resp.posts:
                            mark_sent(post.post_url)
                else:
                    logger.error(f"❌ Failed to send brand message for '{brand_name}' to Telegram")
            else:
                logger.warning(f"⚠️ No posts found for any profiles in brand '{brand_name}', skipping Telegram message.")

            # Save ALL scraped URLs for this brand to output
            if all_scraped_by_platform:
                shared_by_brand[brand_name] = all_scraped_by_platform

            # Inter-brand cooldown sleep
            if brand_idx < len(brands):
                cooldown = 5.0
                logger.info(f"💤 Sleeping for {cooldown} seconds before starting the next brand...")
                await asyncio.sleep(cooldown)

        # Save to output folder with date-wise naming
        from app.telegram_bot.ui_api import save_shared_posts_to_output
        save_shared_posts_to_output(shared_by_brand, is_manual=False, out_filename=out_filename)

        logger.info("\n🏁 Finished processing all brands!")
    finally:
        teardown_run_logging(handler)

if __name__ == "__main__":
    asyncio.run(run_one_by_one())
