"""
Telegram Bot — message formatting and sending logic.
Sends scraped post info to a Telegram channel with rich formatting.
Supports grouped brand messages and individual post messages.
"""

import logging
import os
import asyncio
import threading
from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode

from app.models.schemas import PostItem, ScrapeResponse

logger = logging.getLogger(__name__)

# ── Platform emoji map ───────────────────────────────────────
PLATFORM_EMOJI = {
    "instagram": "📸",
    "youtube": "▶️",
    "facebook": "📘",
    "linkedin": "💼",
    "pinterest": "📌",
}

PLATFORM_LABELS = {
    "instagram": "Instagram",
    "youtube": "YouTube",
    "facebook": "Facebook",
    "linkedin": "LinkedIn",
    "pinterest": "Pinterest",
}

CONTENT_TYPE_EMOJI = {
    "reel": "🎬",
    "short": "🎬",
    "shorts": "🎬",
    "post": "📄",
    "video": "🎥",
    "pin": "📌",
}


from telegram.request import HTTPXRequest
from urllib.parse import urlparse, urlunparse


def get_bot() -> Bot:
    """Create a Telegram Bot instance from env config (direct connection only)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    return Bot(token=token)


def get_channel_id() -> str:
    """Get the target Telegram channel ID from env."""
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    if not channel_id:
        raise RuntimeError(
            "TELEGRAM_CHANNEL_ID is not set in .env. "
            "Run: python run_telegram_bot.py --detect-channel to discover it."
        )
    return channel_id


def _escape_html(text: str) -> str:
    """Escape HTML special chars for Telegram messages."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


PLATFORM_ICONS = {
    "instagram": "📸",
    "facebook":  "📘",
    "linkedin":  "💼",
    "pinterest": "📌",
    "youtube":   "▶️ ",
}

def format_brand_message(
    brand_name: str,
    results: list[ScrapeResponse],
    failed_platforms: Optional[list[str]] = None,
) -> str:
    """
    Build Telegram message with ALL platforms that have a URL.
    Also shows ❌ Failed lines for platforms that were attempted but returned no data.
    """
    lines = []
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🏷️  {brand_name.upper()}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")

    # Group results by platform
    results_by_platform = {r.platform.lower(): r for r in results if r}
    failed_set = set(p.lower() for p in (failed_platforms or []))

    has_any = False
    for platform in ["instagram", "facebook", "linkedin", "pinterest", "youtube"]:
        result = results_by_platform.get(platform)
        icon = PLATFORM_ICONS.get(platform, "🔗")
        cap_name = platform.capitalize()
        if platform == "youtube":
            cap_name = "YouTube"
        elif platform == "linkedin":
            cap_name = "LinkedIn"

        if result and result.posts and len(result.posts) > 0:
            post = result.posts[0]
            url = post.post_url
            date_str = ""
            if post.posted_at:
                cleaned_date = post.posted_at.replace("T00:00:00", "")
                date_str = f" (Published: {cleaned_date})"
            else:
                from datetime import datetime, timezone
                now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                date_str = f" (Scraped: {now_str})"
            lines.append(f"{icon} {cap_name}{date_str}: {url}")
            has_any = True
        elif platform in failed_set:
            lines.append(f"❌ {cap_name}: Failed to scrape")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")

    if not has_any:
        return ""

    return "\n".join(lines)


async def _send_message_with_fallback(
    chat_id: str,
    text: str,
    parse_mode: ParseMode = ParseMode.HTML,
    disable_web_page_preview: bool = True,
) -> bool:
    """
    Sends a message to Telegram trying:
    1. Direct connection (fast timeout: 4s)
    2. Verified working proxies from proxy/working_tg_proxies.txt
    """
    # 1. Try Direct first
    try:
        logger.info(f"📤 Attempting direct Telegram send to {chat_id}...")
        request = HTTPXRequest(connect_timeout=4.0, read_timeout=15.0)
        async with Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"), request=request) as bot:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
            logger.info("✅ Direct Telegram send succeeded!")
            return True
    except Exception as e:
        logger.warning(f"⚠️ Direct Telegram send failed/timed out: {e}")

    # 2. Try verified working proxies
    working_proxies = [
        "socks5://84.47.150.125:1080",
        "http://84.47.150.125:1080",
        "http://92.118.112.32:1082",
        "http://169.212.15.161:5000",
        "http://85.234.100.149:8080",
        "http://2.26.87.216:1080",
        "http://94.158.49.82:3128"
    ]
    
    from pathlib import Path
    working_file = Path("proxy/working_tg_proxies.txt")
    if working_file.exists():
        try:
            with open(working_file, "r") as f:
                file_proxies = [line.strip() for line in f if line.strip()]
            if file_proxies:
                # Prioritize file proxies but merge with default ones
                working_proxies = file_proxies + [p for p in working_proxies if p not in file_proxies]
        except Exception:
            pass

    for proxy_url in working_proxies:
        try:
            logger.info(f"📤 Attempting Telegram send via proxy {proxy_url}...")
            request = HTTPXRequest(proxy=proxy_url, connect_timeout=6.0, read_timeout=15.0)
            async with Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"), request=request) as bot:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                )
                logger.info(f"✅ Telegram send via proxy {proxy_url} succeeded!")
                return True
        except Exception as pe:
            logger.warning(f"⚠️ Proxy {proxy_url} failed: {pe}")

    logger.error("❌ All Telegram sending attempts failed (both direct and all proxies).")
    return False


def build_telegram_message(brand_name: str, results: dict) -> str:
    """
    Build Telegram message with ALL platforms that have a URL.
    Includes platforms regardless of dedup status.
    Only skips platforms that FAILED (no URL found at all).
    """
    response_list = [r for r in results.values() if r]
    return format_brand_message(brand_name, response_list)


async def send_telegram_message(text: str, channel_id: Optional[str] = None) -> bool:
    """Send raw HTML text message to Telegram channel with fallback."""
    target = channel_id or get_channel_id()
    return await _send_message_with_fallback(
        chat_id=target,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


def format_single_platform_message(result: ScrapeResponse) -> str:
    """
    Format a single platform scrape result as a message.
    Used when scraping a single URL (not grouped by brand).
    """
    platform = result.platform.lower()
    emoji = PLATFORM_EMOJI.get(platform, "🌐")
    label = PLATFORM_LABELS.get(platform, platform.capitalize())

    lines = []
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"{emoji} <b>{label}:</b>")

    for post in result.posts:
        date_str = ""
        if post.posted_at:
            cleaned_date = post.posted_at.replace("T00:00:00", "")
            date_str = f" (Published: {cleaned_date})"
        else:
            from datetime import datetime, timezone
            now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            date_str = f" (Scraped: {now_str})"
        lines.append(f"🔗 {post.post_url}{date_str}")

    while lines and lines[-1] == "":
        lines.pop()

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def format_post_message(post: PostItem) -> str:
    """Format a single PostItem into a Telegram message."""
    platform_emoji = PLATFORM_EMOJI.get(post.platform, "🌐")
    platform_name = PLATFORM_LABELS.get(post.platform, post.platform.capitalize())

    date_str = ""
    if post.posted_at:
        cleaned_date = post.posted_at.replace("T00:00:00", "")
        date_str = f" (Published: {cleaned_date})"
    else:
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        date_str = f" (Scraped: {now_str})"

    lines = []
    lines.append(f"{platform_emoji} <b>{platform_name}{date_str}:</b>")
    lines.append(f"🔗 {post.post_url}")

    return "\n".join(lines)


async def send_brand_message(
    brand_name: str,
    results: list[ScrapeResponse],
    channel_id: Optional[str] = None,
    failed_platforms: Optional[list[str]] = None,
) -> bool:
    """Send a grouped brand message to the channel with fallback."""
    target = channel_id or get_channel_id()
    message_text = format_brand_message(brand_name, results, failed_platforms)

    if not message_text:
        logger.warning(f"Empty brand message for '{brand_name}', skipping send")
        return False

    logger.info(f"📤 Sending brand message for '{brand_name}'...")
    # Telegram has a 4096 char limit — split if needed
    if len(message_text) > 4000:
        chunks = _split_message(message_text, 4000)
        all_success = True
        for chunk in chunks:
            success = await _send_message_with_fallback(
                chat_id=target,
                text=chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            if not success:
                all_success = False
        return all_success
    else:
        return await _send_message_with_fallback(
            chat_id=target,
            text=message_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def send_platform_message(
    result: ScrapeResponse,
    channel_id: Optional[str] = None,
) -> bool:
    """Send a single-platform message to the channel with fallback."""
    target = channel_id or get_channel_id()
    message_text = format_single_platform_message(result)
    return await _send_message_with_fallback(
        chat_id=target,
        text=message_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def send_post_to_channel(post: PostItem, channel_id: Optional[str] = None) -> bool:
    """Send a single post to the Telegram channel with fallback."""
    target = channel_id or get_channel_id()
    message_text = format_post_message(post)
    return await _send_message_with_fallback(
        chat_id=target,
        text=message_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )


async def send_summary_to_channel(
    platform: str,
    new_count: int,
    total_scraped: int,
    channel_id: Optional[str] = None,
):
    """Send a brief summary after a scrape batch with fallback."""
    target = channel_id or get_channel_id()
    emoji = PLATFORM_EMOJI.get(platform, "🌐")
    text = (
        f"📊 <b>Scrape Summary</b>\n"
        f"{emoji} {platform.capitalize()}: "
        f"{new_count} new post(s) out of {total_scraped} scraped"
    )
    await _send_message_with_fallback(
        chat_id=target,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def send_admin_message(text: str):
    """Send a message directly to the admin user with fallback."""
    admin_id = os.getenv("TELEGRAM_ADMIN_USER_ID", "").strip()
    if not admin_id:
        logger.warning("TELEGRAM_ADMIN_USER_ID not set, skipping admin message")
        return
    await _send_message_with_fallback(
        chat_id=admin_id,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def detect_channel_id():
    """Helper to detect the numeric channel ID."""
    admin_id = os.getenv("TELEGRAM_ADMIN_USER_ID", "").strip()

    async with get_bot() as bot:
        info = await bot.get_me()
        logger.info(f"🤖 Bot info: @{info.username} (ID: {info.id})")

        if admin_id:
            await bot.send_message(
                chat_id=admin_id,
                text=(
                    "🔍 <b>Channel ID Detection</b>\n\n"
                    "To find your channel's numeric ID:\n"
                    "1. Add this bot as admin to your channel\n"
                    "2. Forward any message from the channel to @userinfobot\n"
                    "3. Copy the channel ID (starts with -100...)\n"
                    "4. Set it in your .env file as TELEGRAM_CHANNEL_ID\n\n"
                    "Or send /chatid in the channel after adding the bot."
                ),
                parse_mode=ParseMode.HTML,
                read_timeout=60,
                connect_timeout=60,
            )
            logger.info(f"📨 Sent instructions to admin user {admin_id}")

        return info


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """Split a long message into chunks at newline boundaries."""
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current)
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        chunks.append(current)
    return chunks


class TelegramAlertHandler(logging.Handler):
    """
    Custom logging Handler that sends WARNING, ERROR, and CRITICAL
    log records directly to the Telegram admin chat.
    """
    _local = threading.local()

    def __init__(self, level=logging.WARNING):
        super().__init__(level)

    def emit(self, record):
        # Prevent recursion if sending a log triggers another log emission
        if getattr(self._local, "is_sending", False):
            return

        # Double check level
        if record.levelno < logging.WARNING:
            return

        # Filter warnings: only allow suspicious or login/scraping issues
        if record.levelno == logging.WARNING:
            msg_lower = record.getMessage().lower()
            keywords = [
                "login", "session", "cookie", "checkpoint", "logged out", 
                "fail", "error", "missing", "redirect", "block", 
                "refused", "timeout", "invalid", "auth"
            ]
            if not any(kw in msg_lower for kw in keywords):
                return

        # Format timestamp
        import datetime
        log_time = datetime.datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')

        # Build alert message text
        emoji = "⚠️" if record.levelno == logging.WARNING else "🚨"
        msg = (
            f"{emoji} <b>SYSTEM LOG ALERT</b>\n"
            f"<b>Time:</b> <code>{log_time}</code>\n"
            f"<b>Level:</b> {record.levelname}\n"
            f"<b>Module:</b> {record.name}\n"
            f"<b>Message:</b>\n<code>{_escape_html(record.getMessage())}</code>"
        )

        self._local.is_sending = True
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Schedule the message send in the running event loop
                loop.create_task(send_admin_message(msg))
            else:
                # Spawn a background thread to send the message synchronously
                def run_in_thread():
                    try:
                        asyncio.run(send_admin_message(msg))
                    except Exception:
                        pass
                threading.Thread(target=run_in_thread, daemon=True).start()
        except Exception:
            pass
        finally:
            self._local.is_sending = False


def setup_telegram_log_handler():
    """Add TelegramAlertHandler to the root logger so all warnings/errors are sent to the admin."""
    root_logger = logging.getLogger()
    
    # Check if we already added it to avoid duplicates
    for handler in root_logger.handlers:
        if isinstance(handler, TelegramAlertHandler):
            return
            
    # Add handler if admin user ID is set
    admin_id = os.getenv("TELEGRAM_ADMIN_USER_ID", "").strip()
    if admin_id:
        handler = TelegramAlertHandler()
        # Use formatting similar to basic config
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
        logger.info("📢 Telegram Log Alert Handler registered successfully.")
