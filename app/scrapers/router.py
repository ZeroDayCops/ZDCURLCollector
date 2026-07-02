"""
Scraper Router
Dispatches scrape requests to the correct platform-specific scraper.
All scrapers are called asynchronously via asyncio.
"""

import asyncio
import logging
from typing import Optional

from app.models.schemas import ScrapeResponse
from app.scrapers.instagram import scrape_instagram
from app.scrapers.youtube import scrape_youtube
from app.scrapers.facebook import scrape_facebook
from app.scrapers.linkedin import scrape_linkedin
from app.scrapers.pinterest import scrape_pinterest

logger = logging.getLogger(__name__)

# YouTube scraper is sync — wrap it
_SYNC_SCRAPERS = {
    "youtube": scrape_youtube,
}

_ASYNC_SCRAPERS = {
    "instagram": scrape_instagram,
    "facebook": scrape_facebook,
    "linkedin": scrape_linkedin,
    "pinterest": scrape_pinterest,
}


async def scrape_profile(
    url: str,
    platform: str,
    max_posts: int = 20,
) -> ScrapeResponse:
    """
    Route a scrape request to the appropriate platform scraper.

    Sync scrapers (Instagram, YouTube) are run in a thread pool executor
    so they don't block the async event loop.
    """
    logger.info(f"🔀 Routing to {platform.upper()} scraper")

    if platform in _SYNC_SCRAPERS:
        scraper_fn = _SYNC_SCRAPERS[platform]
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: scraper_fn(url, max_posts)
        )
        return result

    elif platform in _ASYNC_SCRAPERS:
        scraper_fn = _ASYNC_SCRAPERS[platform]
        return await scraper_fn(url, max_posts)

    else:
        raise ValueError(
            f"No scraper registered for platform: '{platform}'. "
            f"Supported: {list(_SYNC_SCRAPERS) + list(_ASYNC_SCRAPERS)}"
        )
