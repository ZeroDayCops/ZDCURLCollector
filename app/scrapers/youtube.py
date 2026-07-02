"""
YouTube Scraper using yt-dlp
- Works with public channels, no auth needed
- Extracts: video URL, title, thumbnail, upload date, view count
- Handles @handles, /c/, /channel/, /user/ and bare paths
"""

import logging
import re
from typing import Optional

import yt_dlp

from app.models.schemas import PostItem, ScrapeResponse

logger = logging.getLogger(__name__)


def _normalize_youtube_url(url: str) -> str:
    """
    Normalize a YouTube channel/profile URL to target SHORTS only.
    """
    url = url.strip().rstrip("/")

    if "/videos" in url:
        url = url.replace("/videos", "/shorts")
    elif "/shorts" not in url:
        if re.search(r"youtube\.com/@", url):
            url = url + "/shorts"
        elif re.search(r"youtube\.com/(c|channel|user)/", url):
            url = url + "/shorts"
        else:
            match = re.search(r"youtube\.com/([^/?#\s]+)", url)
            if match:
                handle = match.group(1)
                url = f"https://www.youtube.com/@{handle}/shorts"
            else:
                url = url + "/shorts"

    return url


def scrape_youtube(url: str, max_posts: int = 20) -> ScrapeResponse:
    """
    Scrape latest Shorts from a YouTube channel.
    """
    channel_url = _normalize_youtube_url(url)
    logger.info(f"▶️  Scraping YouTube Shorts: {channel_url}")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,          # Don't download, just get metadata
        "playlist_items": f"1-{max_posts}",
        "ignoreerrors": True,
        "socket_timeout": 30,
        "retries": 3,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        },
    }

    posts: list[PostItem] = []
    error_msg: Optional[str] = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)

            if not info:
                raise RuntimeError("yt-dlp returned no info. Channel may not exist or is private.")

            entries = info.get("entries", [])
            if not entries:
                # Try `/shorts` query suffix if not already present
                logger.info("No entries found at normalized URL, attempting fallback...")
                if "/shorts" not in channel_url:
                    alt_url = channel_url + "/shorts"
                    info = ydl.extract_info(alt_url, download=False)
                    entries = info.get("entries", []) if info else []

            logger.info(f"Found {len(entries)} Shorts in listing")

            for entry in entries[:max_posts]:
                if not entry:
                    continue

                video_id = entry.get("id") or entry.get("url", "").split("v=")[-1]
                if not video_id:
                    continue

                video_url = f"https://www.youtube.com/watch?v={video_id}"
                title = entry.get("title") or entry.get("fulltitle") or None

                # Thumbnail
                thumbnail = entry.get("thumbnail")
                if not thumbnail and video_id:
                    thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

                # Upload date: yt-dlp returns YYYYMMDD string
                uploaded_str = entry.get("upload_date")
                posted_at = None
                if uploaded_str and len(uploaded_str) == 8:
                    try:
                        posted_at = f"{uploaded_str[:4]}-{uploaded_str[4:6]}-{uploaded_str[6:8]}T00:00:00"
                    except Exception:
                        pass

                views = entry.get("view_count")

                # Determine if it is a YouTube Short (reel) vs standard video
                is_short = False
                orig_url = entry.get("original_url") or entry.get("webpage_url") or ""
                if "/shorts" in orig_url or "/shorts" in channel_url:
                    is_short = True
                    video_url = f"https://www.youtube.com/shorts/{video_id}"

                posts.append(PostItem(
                    post_url=video_url,
                    caption=title,
                    thumbnail_url=thumbnail,
                    posted_at=posted_at,
                    likes=None,  # yt-dlp flat extract doesn't fetch likes
                    platform="youtube",
                    type="reel" if is_short else "post",
                ))
                logger.debug(f"  ✓ {video_url} | {title}")

    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if "404" in err or "does not exist" in err.lower():
            raise ValueError(f"YouTube channel not found: {url}")
        elif "private" in err.lower():
            raise ValueError(f"YouTube channel is private: {url}")
        elif "geo" in err.lower() or "not available" in err.lower():
            logger.error(f"YouTube geo/availability issue: {e}")
            if not posts:
                raise RuntimeError(f"YouTube content not available in your region: {e}")
            error_msg = f"Some videos may be geo-restricted: {e}"
        else:
            logger.error(f"yt-dlp DownloadError: {e}")
            if not posts:
                raise RuntimeError(f"YouTube scraping failed: {e}")
            error_msg = f"Partial results (yt-dlp error): {e}"
    except Exception as e:
        logger.exception(f"YouTube scraping error: {e}")
        if not posts:
            raise RuntimeError(f"YouTube scraping failed: {e}")
        error_msg = str(e)

    return ScrapeResponse(
        platform="youtube",
        profile_url=url,
        posts_found=len(posts),
        posts=posts,
        scrape_status="success" if not error_msg else "partial",
        message=error_msg,
    )
