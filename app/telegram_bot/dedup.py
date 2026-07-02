import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
DEDUP_PATH = Path("data/sent_posts.json")


def _load() -> dict:
    if not DEDUP_PATH.exists():
        return {"history": []}
    try:
        with open(DEDUP_PATH) as f:
            data = json.load(f)
        # Support both old format (list) and new format (dict)
        if isinstance(data, list):
            return {"history": [{"url": u, "sent_at": ""} for u in data]}
        # Support old dict format mapping URL to timestamp (e.g. {"url": ts})
        if isinstance(data, dict) and "history" not in data:
            history = []
            for u, ts in data.items():
                try:
                    dt_str = datetime.fromtimestamp(ts, timezone.utc).isoformat()
                except Exception:
                    dt_str = ""
                history.append({"url": u, "sent_at": dt_str})
            return {"history": history}
        return data
    except Exception:
        return {"history": []}


def _save(data: dict):
    DEDUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DEDUP_PATH, "w") as f:
        json.dump(data, f, indent=2)


def normalize_url(url: str) -> str:
    """Normalize URLs for comparison (lowercase domains, strip trailing slashes, remove non-FB query params)."""
    if not url:
        return ""
    url = url.strip()
    if url.endswith("/"):
        url = url[:-1]
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        scheme = parsed.scheme.lower()
        path = parsed.path
        if path.endswith("/"):
            path = path[:-1]
            
        # Keep query parameters ONLY for Facebook where fbid/set is required
        query = parsed.query
        if "facebook.com" not in netloc:
            query = ""
            
        return urlunparse((scheme, netloc, path, parsed.params, query, parsed.fragment))
    except Exception:
        return url.lower()


def was_sent_in_last_n_minutes(url: str, minutes: int = 2) -> bool:
    """
    Returns True ONLY if this URL was sent in the last N minutes.
    Used to prevent duplicate sends within the SAME scrape run.
    """
    data = _load()
    now = datetime.now(timezone.utc)
    norm_url = normalize_url(url)
    for entry in data.get("history", []):
        if normalize_url(entry.get("url")) == norm_url:
            sent_at_str = entry.get("sent_at", "")
            if not sent_at_str:
                continue
            try:
                sent_at = datetime.fromisoformat(sent_at_str)
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=timezone.utc)
                diff_minutes = (now - sent_at).total_seconds() / 60
                if diff_minutes < minutes:
                    return True
            except Exception:
                continue
    return False


def mark_sent(url: str):
    """Record that this URL was sent right now."""
    data = _load()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Update existing entry if URL exists, otherwise append
    norm_url = normalize_url(url)
    for entry in data["history"]:
        if normalize_url(entry.get("url")) == norm_url:
            entry["sent_at"] = now_iso
            _save(data)
            return

    data["history"].append({"url": url, "sent_at": now_iso})

    # Keep only last 500 entries to prevent file bloat
    if len(data["history"]) > 500:
        data["history"] = data["history"][-500:]

    _save(data)


def is_new(url: str) -> bool:
    """
    Returns True if URL has NOT been sent to the Telegram group before.
    Performs a permanent history lookup matching normalized URLs.
    """
    data = _load()
    norm_url = normalize_url(url)
    for entry in data.get("history", []):
        if normalize_url(entry.get("url")) == norm_url:
            logger.info(f"[DEDUP] Skipping (already sent previously): {url}")
            return False
    return True


def clear_sent_posts_cache() -> bool:
    """Delete the sent posts database to start clean."""
    if DEDUP_PATH.exists():
        try:
            DEDUP_PATH.unlink()
            logger.info("🗑️ Cleared sent posts cache (data/sent_posts.json) for the new scan.")
            return True
        except Exception as e:
            logger.error(f"⚠️ Failed to clear sent posts cache: {e}")
    return False



# DedupTracker class to preserve backward compatibility if other files import it
class DedupTracker:
    def __init__(self, store_path=None):
        pass

    def is_new(self, url: str) -> bool:
        return is_new(url)

    def mark_sent(self, url: str):
        mark_sent(url)

    def mark_sent_batch(self, urls: list[str]):
        for url in urls:
            mark_sent(url)

    def prune_old(self):
        pass

    def clear(self):
        clear_sent_posts_cache()

    def count(self) -> int:
        data = _load()
        return len(data.get("history", []))
