"""
Automatically detect social media platform from URL
"""

import re
from typing import Optional


PLATFORM_PATTERNS = {
    "instagram": [
        r"(?:https?://)?(?:www\.)?instagram\.com/",
        r"(?:https?://)?instagr\.am/",
    ],
    "youtube": [
        r"(?:https?://)?(?:www\.)?youtube\.com/(?:@|c/|channel/|user/)",
        r"(?:https?://)?(?:www\.)?youtube\.com/[^/]+$",
        r"(?:https?://)?youtu\.be/",
        r"(?:https?://)?(?:www\.)?youtube\.com/$",
    ],
    "facebook": [
        r"(?:https?://)?(?:www\.)?facebook\.com/",
        r"(?:https?://)?(?:www\.)?fb\.com/",
        r"(?:https?://)?(?:www\.)?fb\.watch/",
    ],
    "linkedin": [
        r"(?:https?://)?(?:www\.)?linkedin\.com/(?:in|company|school|pub)/",
        r"(?:https?://)?(?:www\.)?linkedin\.com/",
    ],
    "pinterest": [
        r"(?:https?://)?(?:www\.)?pinterest\.com/",
        r"(?:https?://)?(?:www\.)?pinterest\.[a-z]{2,3}/",
        r"(?:https?://)?pin\.it/",
    ],
}


def detect_platform(url: str) -> Optional[str]:
    """
    Detect platform from URL string.
    Returns platform name (lowercase) or None if unrecognized.
    """
    url = url.strip().lower()

    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return platform

    return None


def extract_username(url: str, platform: str) -> Optional[str]:
    """
    Try to extract username/handle from profile URL.
    """
    url = url.strip().rstrip("/")

    patterns = {
        "instagram": r"instagram\.com/([^/?#]+)",
        "youtube": r"youtube\.com/(?:@|c/|channel/|user/)?([^/?#]+)",
        "facebook": r"facebook\.com/([^/?#]+)",
        "linkedin": r"linkedin\.com/(?:in|company|school)/([^/?#]+)",
        "pinterest": r"pinterest\.(?:com|[a-z]{2,3})/([^/?#]+)",
    }

    pattern = patterns.get(platform)
    if pattern:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1).lstrip("@")

    return None
