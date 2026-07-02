"""
API routes for the Web UI — manual URL input and file upload.
Scrapes profiles and sends grouped results to Telegram.
"""

import asyncio
import io
import logging
import os
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, BackgroundTasks
from pydantic import BaseModel

from app.scrapers.router import scrape_profile
from app.utils.platform_detector import detect_platform
from app.utils.date_parser import parse_relative_date, is_recent_post
from app.telegram_bot.bot import send_brand_message, send_platform_message
from app.telegram_bot.dedup import DedupTracker, clear_sent_posts_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["telegram"])

active_runs: dict[str, dict] = {}

def add_active_run(run_id: str, total_urls: int):
    # Bounded active_runs store to avoid memory leaks
    if len(active_runs) > 50:
        old_keys = list(active_runs.keys())[:10]
        for k in old_keys:
            active_runs.pop(k, None)

    active_runs[run_id] = {
        "status": "running",
        "progress": 0,
        "total": total_urls,
        "total_new_posts": 0,
        "results": [],
        "brand_results": {},
        "brands_processed": 0,
        "total_brands": 0,
        "output_file": None,
        "error": None
    }

@router.get("/status/{run_id}")
async def get_run_status(run_id: str):
    """Retrieve real-time progress and results of a background scrape run."""
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Scraping run not found")
    return active_runs[run_id]


# ── Request / Response Models ─────────────────────────────────

class ManualScrapeRequest(BaseModel):
    brand_name: str = "Manual Scrape"
    urls: list[str]
    max_posts: int = 1


# ── Helpers ───────────────────────────────────────────────────

async def scrape_single_url(url: str, max_posts: int) -> dict:
    """Scrape a single URL and return result dict, retrying up to 5 times on scraper failure."""
    url = url.strip()
    platform = detect_platform(url)
    if not platform:
        return {
            "url": url,
            "platform": "unknown",
            "status": "error",
            "error": f"Could not detect platform from URL: {url}",
            "posts": [],
            "posts_sent": 0,
        }

    max_attempts = 5
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"🔄 Scraping {platform.upper()} (Attempt {attempt}/{max_attempts}): {url}")
            result = await scrape_profile(url=url, platform=platform, max_posts=max_posts)
            return {
                "url": url,
                "platform": platform,
                "status": "success",
                "posts_found": result.posts_found,
                "posts": [p.model_dump() for p in result.posts],
                "posts_sent": 0,
                "scrape_response": result,
            }
        except ValueError as ve:
            # Don't retry user-facing configuration/session errors
            logger.error(f"❌ Scrape failed immediately (ValueError) for {url}: {ve}")
            return {
                "url": url,
                "platform": platform,
                "status": "error",
                "error": str(ve),
                "posts": [],
                "posts_sent": 0,
            }
        except Exception as e:
            last_error = str(e)
            logger.warning(f"⚠️ Scrape attempt {attempt}/{max_attempts} failed for {url}: {last_error}")
            if attempt < max_attempts:
                # Sleep a bit before next attempt
                await asyncio.sleep(3)

    return {
        "url": url,
        "platform": platform,
        "status": "error",
        "error": last_error,
        "posts": [],
        "posts_sent": 0,
    }


def parse_txt_file(content: str) -> dict[str, list[str]]:
    """
    Parse a TXT file into {brand_name: [urls]}.
    Non-URL lines are treated as brand headers (supporting leading # and trailing :),
    while platform labels (e.g. Instagram:) and separators (e.g. ===) are ignored.
    Returns only brands with at least one URL.
    """
    import re
    brands: dict[str, list[str]] = {}
    current_brand = "Default"

    # Known platform labels to ignore
    platform_labels = {
        "instagram", "youtube", "facebook", "pinterest", "linkedin",
        "tiktok", "twitter", "x", "snapchat", "threads",
        "insta", "yt", "fb", "pin", "li"
    }

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        
        # 1. Check if it's a URL
        if line.startswith("http://") or line.startswith("https://"):
            if current_brand not in brands:
                brands[current_brand] = []
            brands[current_brand].append(line)
            continue
        
        # 2. Check if it's a separator line (e.g. ===, ---, ___)
        if re.match(r'^[=\-_*]{3,}$', line):
            continue
            
        # 3. Check if it's a platform label (e.g. Instagram:)
        clean_label = line.rstrip(":").strip().lower()
        if clean_label in platform_labels:
            continue
            
        # 4. Otherwise, it's a brand name
        brand_name = line.lstrip("#").rstrip(":").strip()
        if brand_name:
            current_brand = brand_name
            if current_brand not in brands:
                brands[current_brand] = []

    # Only return brands with at least one URL
    return {brand: urls for brand, urls in brands.items() if urls}



def parse_xlsx_file(file_bytes: bytes) -> dict[str, list[str]]:
    """
    Parse an XLSX file into {brand_name: [urls]}.
    Expected columns: Brand, URL (or first two columns).
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
    ws = wb.active

    brands: dict[str, list[str]] = {}

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return brands

    # Skip header row if it looks like a header
    start = 0
    first_row = rows[0]
    if first_row and isinstance(first_row[0], str):
        first_val = first_row[0].lower()
        if first_val in ("brand", "name", "label", "company"):
            start = 1

    for row in rows[start:]:
        if len(row) < 2:
            continue

        brand = str(row[0]).strip() if row[0] else "Default"
        url = str(row[1]).strip() if row[1] else ""

        if not url or not (url.startswith("http://") or url.startswith("https://")):
            continue

        if brand not in brands:
            brands[brand] = []
        brands[brand].append(url)

    wb.close()
    return brands


def _get_next_output_filename(prefix: str = "file") -> str:
    """
    Generate date-wise sequential output filenames.
    For file uploads: 16junefile1.txt, 16junefile2.txt, ...
    For manual scrapes: 16junemanual1.txt, 16junemanual2.txt, ...
    """
    import re
    from pathlib import Path
    from datetime import datetime

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    day = now.strftime("%d")          # e.g. "16"
    month = now.strftime("%B").lower()  # e.g. "june"
    date_prefix = f"{day}{month}"      # e.g. "16june"

    # Find the highest existing sequence number for today
    pattern = re.compile(rf"^{re.escape(date_prefix)}{re.escape(prefix)}(\d+)\.txt$", re.IGNORECASE)
    max_seq = 0
    if output_dir.exists():
        for f in output_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                max_seq = max(max_seq, int(m.group(1)))

    next_seq = max_seq + 1
    return f"{date_prefix}{prefix}{next_seq}.txt"


def setup_run_logging(prefix: str):
    import logging
    from datetime import datetime
    from pathlib import Path
    
    # 1. Determine date prefix and filename
    out_filename = _get_next_output_filename(prefix)
    log_filename = out_filename.replace(".txt", ".log")
    
    # 2. Create date-wise folder: logs/YYYY-MM-DD/
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    log_dir = Path("logs") / date_str
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / log_filename
    
    # 3. Create file handler
    handler = logging.FileHandler(log_file, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    
    # 4. Add to root logger
    logging.getLogger().addHandler(handler)
    
    return handler, log_file, out_filename


def teardown_run_logging(handler):
    import logging
    if handler:
        try:
            handler.close()
        except Exception:
            pass
        try:
            logging.getLogger().removeHandler(handler)
        except Exception:
            pass


def save_shared_posts_to_output(shared_by_brand: dict[str, dict[str, list[str]]], is_manual: bool = False, out_filename: Optional[str] = None) -> str:
    """
    Save the shared/scraped posts to output/<date><type><seq>.txt.
    Examples: 16junefile1.txt, 16junemanual1.txt
    Format:
    MAHAVIR NX
    
    Instagram:
    https://www.instagram.com/reel/...
    
    ================================================
    """
    from pathlib import Path
    from datetime import datetime

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not out_filename:
        prefix = "manual" if is_manual else "file"
        out_filename = _get_next_output_filename(prefix)
    out_file = output_dir / out_filename

    content_lines = []
    
    if not shared_by_brand:
        content_lines.append(f"# No new posts shared on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    else:
        for brand_name, platforms in shared_by_brand.items():
            if content_lines:
                content_lines.append("\n" + "="*48 + "\n")
            content_lines.append(brand_name + "\n")
            
            for platform_name, urls in platforms.items():
                content_lines.append(f"\n{platform_name.capitalize()}:\n")
                if not urls:
                    content_lines.append("⚠️ No new posts found\n")
                else:
                    for url in urls:
                        content_lines.append(url + "\n")

    file_content = "".join(content_lines)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(file_content)

    logger.info(f"📝 Output saved to: {out_file}")
    return str(out_file)


# ── API Endpoints ─────────────────────────────────────────────

async def background_scrape_and_post(run_id: str, brand_name: str, urls: list[str], max_posts: int):
    """Background task to run manual scrape and post results to Telegram."""
    max_posts = 1
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        active_runs[run_id]["status"] = "failed"
        active_runs[run_id]["error"] = "TELEGRAM_CHANNEL_ID not configured"
        return

    handler, log_file, out_filename = setup_run_logging("manual")
    clear_sent_posts_cache()
    logger.info(f"📥 [BG RUN {run_id}] Manual scrape started: brand='{brand_name}', {len(urls)} URLs. Logging to {log_file}")

    from app.telegram_bot.dedup import mark_sent, is_new

    results = []
    all_scrape_responses = []
    all_scraped_by_platform: dict[str, list[str]] = {}

    try:
        # Pre-initialize platform lists to ensure they always show up in the output report
        for url in urls:
            plat = detect_platform(url)
            if plat:
                all_scraped_by_platform[plat] = []

        for url_idx, url in enumerate(urls, 1):
            result = await scrape_single_url(url, max_posts)
            
            if result["status"] == "success" and "scrape_response" in result:
                scrape_resp = result.pop("scrape_response")
                platform = scrape_resp.platform
                if platform not in all_scraped_by_platform:
                    all_scraped_by_platform[platform] = []

                if scrape_resp.posts:
                    # Filter posts by date recency (4 days)
                    recent_posts = [p for p in scrape_resp.posts if is_recent_post(p.posted_at)]
                    scrape_resp.posts = recent_posts

                    # Record ALL scraped posts in the output tracker (formatted with dates)
                    for p in scrape_resp.posts:
                        date_suffix = ""
                        if p.posted_at:
                            date_str = p.posted_at.split(" ")[0].split("T")[0]
                            date_suffix = f" ({date_str})"
                        all_scraped_by_platform[platform].append(f"{p.post_url}{date_suffix}")

                    new_posts = [p for p in scrape_resp.posts if is_new(p.post_url)]
                    if new_posts:
                        scrape_resp.posts = new_posts
                        all_scrape_responses.append(scrape_resp)
                        result["posts_sent"] = len(new_posts)
                        result["posts"] = [p.model_dump() for p in new_posts]
                    else:
                        result["posts_sent"] = 0
                        result["posts"] = []
                else:
                    result["posts_sent"] = 0
                    result["posts"] = []
            else:
                if "scrape_response" in result:
                    result.pop("scrape_response")
                result["posts_sent"] = 0
                # Track failed platforms in output
                platform = result.get("platform", "unknown")
                if platform != "unknown":
                    if platform not in all_scraped_by_platform:
                        all_scraped_by_platform[platform] = []
                    all_scraped_by_platform[platform].append("❌ Failed")
                
            results.append(result)

            # Update progress in store
            active_runs[run_id]["progress"] = url_idx
            active_runs[run_id]["results"] = results

            # Delay between scrapes (optimized to 4 to 8 seconds)
            import random
            delay_sec = random.randint(4, 8)
            logger.info(f"⏳ Human simulation: sleeping for {delay_sec} seconds before the next profile URL...")
            await asyncio.sleep(delay_sec)

        # Collect failed platforms for error reporting
        failed_platforms = [
            r["platform"] for r in results
            if r.get("status") == "error" and r.get("platform", "unknown") != "unknown"
        ]

        total_sent = 0
        if all_scrape_responses:
            success = await send_brand_message(
                brand_name=brand_name,
                results=all_scrape_responses,
                channel_id=channel_id,
                failed_platforms=failed_platforms,
            )
            if success:
                for resp in all_scrape_responses:
                    for post in resp.posts:
                        mark_sent(post.post_url)
                        total_sent += 1

        # Save ALL scraped URLs to output file
        shared_by_brand = {}
        if all_scraped_by_platform:
            shared_by_brand[brand_name] = all_scraped_by_platform

        out_filepath = save_shared_posts_to_output(shared_by_brand, is_manual=True, out_filename=out_filename)
        from pathlib import Path
        out_filename = Path(out_filepath).name

        # Complete the run
        active_runs[run_id]["status"] = "completed"
        active_runs[run_id]["total_new_posts"] = total_sent
        active_runs[run_id]["output_file"] = out_filename
    except Exception as e:
        logger.exception(f"Exception in background run {run_id}: {e}")
        active_runs[run_id]["status"] = "failed"
        active_runs[run_id]["error"] = str(e)
    finally:
        teardown_run_logging(handler)





@router.post("/scrape-and-post")
async def scrape_and_post(request: ManualScrapeRequest, background_tasks: BackgroundTasks):
    """
    Queue manual scrape URLs entered in the UI to run as a background task.
    Returns the run_id immediately.
    """
    import time
    run_id = f"run_manual_{int(time.time())}"
    add_active_run(run_id, len(request.urls))

    background_tasks.add_task(
        background_scrape_and_post,
        run_id,
        request.brand_name,
        request.urls,
        request.max_posts
    )

    return {
        "status": "running",
        "run_id": run_id,
        "message": "Scraping task started in the background."
    }


async def background_upload_and_post(run_id: str, brands: dict[str, list[str]], max_posts: int):
    """Background task to run file upload scrape and post results to Telegram."""
    max_posts = 1
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        active_runs[run_id]["status"] = "failed"
        active_runs[run_id]["error"] = "TELEGRAM_CHANNEL_ID not configured"
        return

    logger.info(f"📥 [BG RUN {run_id}] File upload: {len(brands)} brands")

    from app.telegram_bot.dedup import mark_sent, is_new

    brand_results = {}
    total_sent = 0
    brands_processed = 0
    shared_by_brand = {}
    processed_count = 0

    for brand_name, urls in brands.items():
        logger.info(f"🏷️  Processing brand: {brand_name} ({len(urls)} URLs)")
        results = []
        all_scrape_responses = []
        all_scraped_by_platform: dict[str, list[str]] = {}

        # Pre-initialize platform lists to ensure they always show up in the output report
        for url in urls:
            plat = detect_platform(url)
            if plat:
                all_scraped_by_platform[plat] = []

        for url in urls:
            result = await scrape_single_url(url, max_posts)
            
            if result["status"] == "success" and "scrape_response" in result:
                scrape_resp = result.pop("scrape_response")
                platform = scrape_resp.platform
                if platform not in all_scraped_by_platform:
                    all_scraped_by_platform[platform] = []

                if scrape_resp.posts:
                    # Filter posts by date recency (4 days)
                    recent_posts = [p for p in scrape_resp.posts if is_recent_post(p.posted_at)]
                    scrape_resp.posts = recent_posts

                    # Record ALL scraped posts in the output tracker (formatted with dates)
                    for p in scrape_resp.posts:
                        date_suffix = ""
                        if p.posted_at:
                            date_str = p.posted_at.split(" ")[0].split("T")[0]
                            date_suffix = f" ({date_str})"
                        all_scraped_by_platform[platform].append(f"{p.post_url}{date_suffix}")

                    new_posts = [p for p in scrape_resp.posts if is_new(p.post_url)]
                    if new_posts:
                        scrape_resp.posts = new_posts
                        all_scrape_responses.append(scrape_resp)
                        result["posts_sent"] = len(new_posts)
                        result["posts"] = [p.model_dump() for p in new_posts]
                    else:
                        result["posts_sent"] = 0
                        result["posts"] = []
                else:
                    result["posts_sent"] = 0
                    result["posts"] = []
            else:
                if "scrape_response" in result:
                    result.pop("scrape_response")
                result["posts_sent"] = 0
                # Track failed platforms in output
                platform = result.get("platform", "unknown")
                if platform != "unknown":
                    if platform not in all_scraped_by_platform:
                        all_scraped_by_platform[platform] = []
                    all_scraped_by_platform[platform].append("❌ Failed")
                
            results.append(result)
            processed_count += 1
            active_runs[run_id]["progress"] = processed_count
            brand_results[brand_name] = results
            active_runs[run_id]["brand_results"] = brand_results
            
            # Delay between URLs within a brand to support larger lists (74 profiles) in ~45 minutes (10 to 18 seconds)
            import random
            delay_sec = random.randint(10, 18)
            logger.info(f"⏳ Human simulation: sleeping for {delay_sec} seconds before the next URL in brand...")
            await asyncio.sleep(delay_sec)

        # Collect failed platforms for error reporting in Telegram message
        failed_platforms = [
            r["platform"] for r in results
            if r.get("status") == "error" and r.get("platform", "unknown") != "unknown"
        ]

        # Send grouped brand message (even if some platforms failed, send what we have)
        if all_scrape_responses:
            success = await send_brand_message(
                brand_name=brand_name,
                results=all_scrape_responses,
                channel_id=channel_id,
                failed_platforms=failed_platforms,
            )
            if success:
                brands_processed += 1
                for resp in all_scrape_responses:
                    for post in resp.posts:
                        mark_sent(post.post_url)
                        total_sent += 1

        # Save ALL scraped URLs for this brand to output (not just sent ones)
        if all_scraped_by_platform:
            shared_by_brand[brand_name] = all_scraped_by_platform

        # Delay between different brands (15 to 30 seconds)
        import random
        brand_delay = random.randint(15, 30)
        logger.info(f"⏳ Human simulation: sleeping for {brand_delay} seconds before processing the next brand...")
        await asyncio.sleep(brand_delay)

    out_filepath = save_shared_posts_to_output(shared_by_brand, is_manual=False)
    from pathlib import Path
    out_filename = Path(out_filepath).name

    # Complete the run
    active_runs[run_id]["status"] = "completed"
    active_runs[run_id]["brands_processed"] = brands_processed
    active_runs[run_id]["total_new_posts"] = total_sent
    active_runs[run_id]["output_file"] = out_filename


@router.post("/upload-and-post")
async def upload_and_post(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    max_posts: int = Form(1),
):
    """
    Upload a TXT or XLSX file with brand URLs, parse it, and queue scraping in the background.
    Returns the run_id immediately.
    """
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        raise HTTPException(status_code=500, detail="TELEGRAM_CHANNEL_ID not configured")

    filename = file.filename.lower()
    file_bytes = await file.read()

    # Parse file into {brand: [urls]}
    if filename.endswith(".txt"):
        content = file_bytes.decode("utf-8", errors="ignore")
        brands = parse_txt_file(content)
    elif filename.endswith((".xlsx", ".xls")):
        brands = parse_xlsx_file(file_bytes)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use .txt or .xlsx")

    if not brands:
        raise HTTPException(status_code=400, detail="No valid URLs found in the file")

    total_urls = sum(len(v) for v in brands.values())
    logger.info(f"📁 File upload: {len(brands)} brand(s), {total_urls} URLs")

    import time
    run_id = f"run_upload_{int(time.time())}"
    add_active_run(run_id, total_urls)
    
    # Pre-populate fields for status tracking
    active_runs[run_id]["total_brands"] = len(brands)

    background_tasks.add_task(
        background_upload_and_post,
        run_id,
        brands,
        max_posts
    )

    return {
        "status": "running",
        "run_id": run_id,
        "message": "File processing and scraping started in the background."
    }


# ── Chrome Extension Integrations ──────────────────────────────

class ExtensionSubmitRequest(BaseModel):
    profile_url: str
    platform: str
    urls: list[str]


@router.post("/extension/submit")
async def extension_submit(request: ExtensionSubmitRequest):
    """
    Receive scraped post URLs from the Chrome Extension helper.
    Checks deduplication, records them, and returns new vs duplicate urls.
    """
    logger.info(f"🔌 Received extension links for {request.profile_url} ({len(request.urls)} links)")
    
    from app.telegram_bot.dedup import is_new, mark_sent

    new_urls = []
    duplicate_urls = []
    
    for url in request.urls:
        if is_new(url):
            new_urls.append(url)
            mark_sent(url)  # Mark as seen so they are not new next time
        else:
            duplicate_urls.append(url)
            
    logger.info(f"✨ Processed {request.profile_url}: {len(new_urls)} new, {len(duplicate_urls)} duplicate(s)")
    return {
        "status": "ok",
        "new_urls": new_urls,
        "duplicate_urls": duplicate_urls,
        "total_count": len(request.urls)
    }

