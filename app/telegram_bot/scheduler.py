"""
Scheduler — periodically scrapes configured profiles and posts new content to Telegram.
Uses APScheduler with AsyncIOScheduler for non-blocking operation.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from app.scrapers.router import scrape_profile
from app.utils.platform_detector import detect_platform
from app.telegram_bot.bot import send_post_to_channel, send_summary_to_channel, send_admin_message
from app.telegram_bot.dedup import DedupTracker, clear_sent_posts_cache

logger = logging.getLogger(__name__)

PROFILES_CONFIG_PATH = Path("config/profiles.json")


def load_profiles() -> list[dict]:
    """Load profile URLs from config/profiles.json."""
    if not PROFILES_CONFIG_PATH.exists():
        logger.error(f"❌ Profiles config not found: {PROFILES_CONFIG_PATH}")
        return []

    try:
        with open(PROFILES_CONFIG_PATH, "r") as f:
            data = json.load(f)
        profiles = data.get("profiles", [])
        logger.info(f"📋 Loaded {len(profiles)} profiles from config")
        return profiles
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"❌ Failed to load profiles config: {e}")
        return []


async def scrape_and_post_single(
    profile: dict,
    tracker: DedupTracker,
    channel_id: str,
) -> tuple[int, int]:
    """
    Scrape a single profile and post new content to Telegram.
    Returns (new_posts_sent, total_scraped).
    """
    url = profile.get("url", "").strip()
    max_posts = profile.get("max_posts", 1)
    label = profile.get("label", url)

    if not url:
        logger.warning("⚠️  Skipping profile with empty URL")
        return 0, 0

    platform = detect_platform(url)
    if not platform:
        logger.warning(f"⚠️  Could not detect platform for: {url}")
        return 0, 0

    logger.info(f"🔄 Scraping {platform.upper()}: {label}")

    try:
        result = await scrape_profile(url=url, platform=platform, max_posts=max_posts)
    except Exception as e:
        logger.error(f"❌ Scrape failed for {label}: {e}")
        return 0, 0

    total_scraped = len(result.posts)
    new_sent = 0

    for post in result.posts:
        if tracker.is_new(post.post_url):
            success = await send_post_to_channel(post, channel_id=channel_id)
            if success:
                tracker.mark_sent(post.post_url)
                new_sent += 1
                # Small delay between messages to avoid Telegram rate limits
                await asyncio.sleep(1.5)

    logger.info(
        f"✅ {platform.upper()} done: {new_sent} new / {total_scraped} total"
    )
    return new_sent, total_scraped


async def run_scrape_cycle():
    """
    Execute a full scrape cycle across all configured profiles.
    This is called by the scheduler on each interval tick.
    """
    clear_sent_posts_cache()
    logger.info("=" * 60)
    logger.info("🔄 Starting scheduled scrape cycle...")
    logger.info("=" * 60)

    channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        logger.error(
            "❌ TELEGRAM_CHANNEL_ID not set. Cannot post to channel. "
            "Run: python run_telegram_bot.py --detect-channel"
        )
        return

    profiles = load_profiles()
    if not profiles:
        logger.warning("⚠️  No profiles configured. Add URLs to config/profiles.json")
        return

    tracker = DedupTracker()
    tracker.prune_old()  # Clean up old entries

    total_new = 0
    total_scraped = 0

    for profile in profiles:
        try:
            new, scraped = await scrape_and_post_single(
                profile=profile,
                tracker=tracker,
                channel_id=channel_id,
            )
            total_new += new
            total_scraped += scraped
        except Exception as e:
            label = profile.get("label", profile.get("url", "unknown"))
            logger.error(f"❌ Error processing {label}: {e}")

        # Delay between profiles (60 to 120 seconds to prevent account restrictions)
        import random
        delay_sec = random.randint(60, 120)
        logger.info(f"⏳ Sleeping for {delay_sec} seconds before scheduled scrape of next profile...")
        await asyncio.sleep(delay_sec)

    logger.info(f"🏁 Scrape cycle complete: {total_new} new posts sent, {total_scraped} total scraped")
    logger.info(f"📊 Dedup tracker has {tracker.count()} tracked post URLs")

    # Send summary to admin
    if total_new > 0:
        await send_admin_message(
            f"📊 <b>Scrape Cycle Complete</b>\n\n"
            f"🆕 {total_new} new posts sent to channel\n"
            f"📄 {total_scraped} total posts scraped\n"
            f"📋 {tracker.count()} posts tracked in dedup store"
        )
