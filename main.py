"""
Social Media Post Scraper - FastAPI Application
Supports: Instagram, YouTube, Facebook, LinkedIn, Pinterest
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models.schemas import ScrapeRequest, ScrapeResponse, ErrorResponse
from app.scrapers.router import scrape_profile
from app.utils.platform_detector import detect_platform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

from app.telegram_bot.bot import setup_telegram_log_handler
setup_telegram_log_handler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Social Scraper API starting up...")
    yield
    logger.info("🛑 Social Scraper API shutting down...")


app = FastAPI(
    title="Social Media Post Scraper",
    description="Scrape latest posts from Instagram, YouTube, Facebook, LinkedIn, Pinterest",
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


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Social Scraper API is running"}


@app.post(
    "/recent-posts",
    response_model=ScrapeResponse,
    summary="Get latest 20 posts from a social media profile",
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    }
)
async def recent_posts(request: ScrapeRequest):
    """
    Scrape the latest 20 posts from a social media profile URL.

    Supported platforms:
    - **Instagram**: Requires IG credentials in environment
    - **YouTube**: Public channels, no auth needed
    - **Facebook**: Requires saved Playwright session cookies
    - **LinkedIn**: Requires saved Playwright session cookies
    - **Pinterest**: Public boards only
    """
    url = str(request.url).strip()
    logger.info(f"📥 Scrape request received for: {url}")

    platform = detect_platform(url)
    if not platform:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported or unrecognized platform URL: {url}. "
                   f"Supported: instagram, youtube, facebook, linkedin, pinterest"
        )

    logger.info(f"🔍 Detected platform: {platform.upper()}")

    try:
        result = await scrape_profile(url=url, platform=platform, max_posts=request.max_posts)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected error scraping {url}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )