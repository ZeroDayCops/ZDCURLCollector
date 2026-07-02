"""
Telegram Bot Runner — Standalone entry point.
Starts the scheduled scraper and posts results to Telegram.

Usage:
    python run_telegram_bot.py                  # Start the scheduled bot
    python run_telegram_bot.py --once           # Run a single scrape cycle and exit
    python run_telegram_bot.py --detect-channel # Detect channel ID and exit
"""

import argparse
import asyncio
import logging
import os
import signal
import sys

from dotenv import load_dotenv

# Load .env before any app imports
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("telegram_bot")

from app.telegram_bot.bot import setup_telegram_log_handler
setup_telegram_log_handler()


async def run_once():
    """Run a single scrape cycle and exit."""
    from app.telegram_bot.scheduler import run_scrape_cycle
    logger.info("🔄 Running single scrape cycle...")
    await run_scrape_cycle()
    logger.info("✅ Single cycle complete. Exiting.")


async def run_detect_channel():
    """Detect channel ID and send instructions to admin."""
    from app.telegram_bot.bot import detect_channel_id
    logger.info("🔍 Detecting channel ID...")
    info = await detect_channel_id()
    logger.info(f"🤖 Bot: @{info.username} (ID: {info.id})")
    logger.info(
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "  To find your channel ID:\n"
        "  1. Add the bot as admin to your channel\n"
        "  2. Forward a channel message to @userinfobot\n"
        "  3. Copy the numeric ID (starts with -100)\n"
        "  4. Set TELEGRAM_CHANNEL_ID in .env\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )


async def run_scheduled():
    """Run the bot with APScheduler on an interval."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.telegram_bot.scheduler import run_scrape_cycle
    from app.telegram_bot.bot import send_admin_message
    from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
    from telegram import Update

    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "🛡️ <b>ZDC Zero Day Cops</b>\n\n"
            "Welcome to ZDC (Zero Day Cops) Collector.\n"
            "We are a private intelligence and alert monitoring system. "
            "Our automated bot collects posts and media reels from social platforms, "
            "tracks new items, and alerts ZDC operators on any system issues."
        )
        await update.message.reply_text(text, parse_mode="HTML")

    interval_minutes = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "30"))

    channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        logger.error(
            "❌ TELEGRAM_CHANNEL_ID is not set in .env!\n"
            "   Run: python run_telegram_bot.py --detect-channel\n"
            "   Then set TELEGRAM_CHANNEL_ID in .env and restart."
        )
        sys.exit(1)

    # Initialize Telegram Bot Command Polling
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start_command))

    logger.info("🤖 Starting Telegram Bot polling loop for commands...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=["message"])

    # Create scheduler
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        run_scrape_cycle,
        trigger="interval",
        minutes=interval_minutes,
        id="scrape_cycle",
        name=f"Scrape every {interval_minutes} minutes",
        max_instances=1,  # Prevent overlapping runs
    )

    logger.info("=" * 60)
    logger.info("🤖 Social Media Scraper — Telegram Bot")
    logger.info(f"⏰ Scrape interval: every {interval_minutes} minutes")
    logger.info(f"📢 Channel ID: {channel_id}")
    logger.info("=" * 60)

    # Notify admin
    await send_admin_message(
        f"🟢 <b>Bot Started</b>\n\n"
        f"⏰ Scraping every {interval_minutes} minutes\n"
        f"📢 Posting to channel: <code>{channel_id}</code>\n\n"
        f"Running initial scrape now..."
    )

    # Run initial scrape immediately
    logger.info("🚀 Running initial scrape cycle...")
    await run_scrape_cycle()

    # Start the scheduler for subsequent runs
    scheduler.start()
    logger.info(f"✅ Scheduler started. Next run in {interval_minutes} minutes.")

    # Keep the process alive
    stop_event = asyncio.Event()

    def handle_shutdown(sig, frame):
        logger.info(f"\n🛑 Received {signal.Signals(sig).name}. Shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logger.info("🛑 Shutting down Telegram bot polling & scheduler...")
        scheduler.shutdown(wait=False)
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

    logger.info("👋 Bot stopped. Goodbye!")


def main():
    parser = argparse.ArgumentParser(
        description="Telegram Bot — Auto-scrape and post to channel",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scrape cycle and exit",
    )
    parser.add_argument(
        "--detect-channel",
        action="store_true",
        help="Detect channel ID and send instructions",
    )

    args = parser.parse_args()

    if args.detect_channel:
        asyncio.run(run_detect_channel())
    elif args.once:
        asyncio.run(run_once())
    else:
        asyncio.run(run_scheduled())


if __name__ == "__main__":
    main()
