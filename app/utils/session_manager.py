"""
Playwright Session/Cookie Manager
Saves and loads browser cookies for Facebook, LinkedIn, Pinterest
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path(os.getenv("SESSIONS_DIR", "./sessions"))


def get_session_path(platform: str) -> Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SESSIONS_DIR / f"{platform}_session.json"


def save_session(platform: str, cookies: list[dict], user_agent: Optional[str] = None) -> bool:
    """Save Playwright cookies and user agent to disk."""
    try:
        path = get_session_path(platform)
        data = {
            "user_agent": user_agent,
            "cookies": cookies,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"✅ Saved session for {platform} (cookies: {len(cookies)}, UA: {user_agent})")
        return True
    except Exception as e:
        logger.error(f"Failed to save session for {platform}: {e}")
        return False


def load_session(platform: str) -> Optional[dict]:
    """Load Playwright session (cookies and user agent) from disk."""
    path = get_session_path(platform)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        elif isinstance(data, list):
            # Backward compatibility for flat list of cookies
            return {"cookies": data, "user_agent": None}
        return None
    except Exception as e:
        logger.error(f"Failed to load session for {platform}: {e}")
        return None


def save_cookies(platform: str, cookies: list[dict]) -> bool:
    """Legacy wrapper to save Playwright cookies to disk."""
    return save_session(platform, cookies)


def load_cookies(platform: str) -> Optional[list[dict]]:
    """Legacy wrapper to load Playwright cookies from disk."""
    session = load_session(platform)
    return session["cookies"] if session else None


def session_exists(platform: str) -> bool:
    return get_session_path(platform).exists()


# ── Persistent Profile Management ──────────────────────────────

PROFILES_DIR = SESSIONS_DIR / "profiles"
_last_profile_index = {}


def get_profile_path(platform: str, profile_name: str) -> Path:
    """Get the absolute path for a persistent browser profile directory."""
    path = PROFILES_DIR / platform / profile_name
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def list_profiles(platform: str) -> list[str]:
    """List all available profile names for a platform."""
    platform_dir = PROFILES_DIR / platform
    if not platform_dir.exists():
        return []
    return [d.name for d in platform_dir.iterdir() if d.is_dir()]


def get_next_profile(platform: str) -> Optional[str]:
    """Get the next profile name to use (round-robin) or None if no profiles exist."""
    profiles = list_profiles(platform)
    if not profiles:
        return None
    
    profiles.sort()
    
    global _last_profile_index
    if platform not in _last_profile_index:
        _last_profile_index[platform] = 0
    else:
        _last_profile_index[platform] = (_last_profile_index[platform] + 1) % len(profiles)
        
    idx = _last_profile_index[platform]
    if idx >= len(profiles):
        idx = 0
        _last_profile_index[platform] = 0
        
    return profiles[idx]


def has_persistent_profiles(platform: str) -> bool:
    """Check if any persistent browser profiles exist for the platform."""
    return len(list_profiles(platform)) > 0

