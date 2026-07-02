"""
Social Media Post Scraper - FastAPI Application
Supports: Instagram, YouTube, Facebook, LinkedIn, Pinterest
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.models.schemas import ScrapeRequest, ScrapeResponse, ErrorResponse
from app.scrapers.router import scrape_profile
from app.utils.platform_detector import detect_platform

# Load .env file if present
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

from app.telegram_bot.bot import setup_telegram_log_handler
setup_telegram_log_handler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown events."""
    logger.info("🚀 Social Scraper API starting up...")

    # Ensure sessions directory exists
    sessions_dir = Path(os.getenv("SESSIONS_DIR", "./sessions"))
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Check for session cookies of all platforms
    from app.utils.session_manager import session_exists
    for platform in ["instagram", "facebook", "linkedin", "pinterest"]:
        emoji = {"instagram": "📷", "facebook": "📘", "linkedin": "💼", "pinterest": "📌"}[platform]
        if session_exists(platform):
            logger.info(f"{emoji} {platform.capitalize()} session cookies found")
        else:
            if platform == "pinterest":
                logger.info(f"{emoji} Pinterest does not require login (optional)")
            else:
                logger.warning(f"⚠️  No {platform.capitalize()} session cookies found. Run: python -m app.tools.login_helper {platform}")

    # Check for Playwright browser
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            await browser.close()
            logger.info("✅ Playwright Chromium is available")
    except Exception as e:
        logger.warning(
            f"⚠️  Playwright Chromium not available: {e}. "
            "Facebook/LinkedIn/Pinterest scrapers may fail. "
            "Run: playwright install chromium"
        )

    yield
    logger.info("🛑 Social Scraper API shutting down...")


app = FastAPI(
    title="Social Media Post Scraper",
    description=(
        "Scrape latest posts from Instagram, YouTube, Facebook, LinkedIn, Pinterest. "
        "Returns real post URLs with captions/titles — no fake data."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Telegram UI API routes ─────────────────────────────────────
from app.telegram_bot.ui_api import router as telegram_router
app.include_router(telegram_router)

# ── Serve static UI & output files ────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# Ensure output directory exists and mount it
os.makedirs("output", exist_ok=True)
app.mount("/output", StaticFiles(directory="output"), name="output")


@app.get("/", include_in_schema=False)
async def serve_ui():
    """Serve the web UI."""
    return FileResponse("static/index.html")


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "message": "Social Scraper API is running",
        "supported_platforms": ["instagram", "youtube", "facebook", "linkedin", "pinterest"],
    }


@app.post(
    "/recent-posts",
    response_model=ScrapeResponse,
    summary="Get latest posts from a social media profile",
    responses={
        400: {"model": ErrorResponse, "description": "Bad request — invalid URL or unsupported platform"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Scraper error"},
    }
)
async def recent_posts(request: ScrapeRequest):
    """
    Scrape the latest posts from a social media profile URL.

    **Supported platforms:**
    - **Instagram**: Requires saved Playwright session cookies
    - **YouTube**: Public channels, no auth needed
    - **Facebook**: Requires saved Playwright session cookies
    - **LinkedIn**: Requires saved Playwright session cookies
    - **Pinterest**: Public boards only

    **Example request:**
    ```json
    {
        "url": "https://www.instagram.com/abhivadan.store/",
        "max_posts": 20
    }
    ```
    """
    url = str(request.url).strip()
    logger.info(f"📥 Scrape request received for: {url}")

    platform = detect_platform(url)
    if not platform:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Unsupported platform",
                "url": url,
                "message": (
                    f"Could not detect platform from URL: {url}. "
                    f"Supported: instagram, youtube, facebook, linkedin, pinterest"
                ),
                "examples": [
                    "https://www.instagram.com/username/",
                    "https://www.youtube.com/@channelname",
                    "https://www.facebook.com/pagename",
                    "https://www.linkedin.com/in/username/",
                    "https://www.pinterest.com/username/",
                ],
            }
        )

    logger.info(f"🔍 Detected platform: {platform.upper()}")

    try:
        result = await scrape_profile(url=url, platform=platform, max_posts=request.max_posts)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "Bad request", "detail": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"error": "Scraper error", "detail": str(e)})
    except Exception as e:
        logger.exception(f"Unexpected error scraping {url}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Unexpected error", "detail": str(e)}
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )
