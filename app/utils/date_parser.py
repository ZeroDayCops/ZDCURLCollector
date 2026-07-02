"""
Date Parser Utility
Parses relative time strings (e.g. "2h", "2 days ago") and absolute dates
into standardized YYYY-MM-DD strings.
"""

import re
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)

def parse_relative_date(text: str) -> str:
    """
    Parse a relative or absolute date/time string into a YYYY-MM-DD string.
    Supports formats like:
      - "2h", "5 hours ago", "3 mins"
      - "1d", "Yesterday at 12:30 PM", "3 days ago"
      - "1w", "2 weeks ago"
      - "June 14 at 10:24 AM", "14 June"
    If it cannot parse, it returns the trimmed original string.
    """
    if not text:
        return ""
    
    text = text.strip()
    # Split by common separators (like bullet points on LinkedIn)
    if "•" in text:
        text = text.split("•")[0].strip()
        
    text_lower = text.lower()
    now = datetime.now(timezone.utc)
    
    try:
        # 1. Minutes
        m = re.match(r'^(\d+)\s*(m|min|minute|minutes|mins)\b', text_lower)
        if m:
            val = int(m.group(1))
            dt = now - timedelta(minutes=val)
            return dt.strftime('%Y-%m-%d')
            
        # 2. Hours
        m = re.match(r'^(\d+)\s*(h|hr|hour|hours|hrs)\b', text_lower)
        if m:
            val = int(m.group(1))
            dt = now - timedelta(hours=val)
            return dt.strftime('%Y-%m-%d')
            
        # 3. Days
        m = re.match(r'^(\d+)\s*(d|day|days)\b', text_lower)
        if m:
            val = int(m.group(1))
            dt = now - timedelta(days=val)
            return dt.strftime('%Y-%m-%d')
            
        # 4. Weeks
        m = re.match(r'^(\d+)\s*(w|week|weeks)\b', text_lower)
        if m:
            val = int(m.group(1))
            dt = now - timedelta(weeks=val)
            return dt.strftime('%Y-%m-%d')
            
        # 5. Yesterday
        if "yesterday" in text_lower:
            dt = now - timedelta(days=1)
            return dt.strftime('%Y-%m-%d')
            
        # 6. Today
        if "today" in text_lower:
            return now.strftime('%Y-%m-%d')
            
        # 7. Absolute formats, e.g., "June 14"
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        for m_idx, month in enumerate(months, 1):
            if month in text_lower:
                digits = re.findall(r'\d+', text_lower)
                if digits:
                    day = None
                    year = None
                    nums = [int(d) for d in digits]
                    
                    # Try to locate a 4-digit year
                    for n in nums:
                        if 2000 <= n <= 2100:
                            year = n
                            break
                    
                    # Try to locate a day of the month (excluding the identified year)
                    for n in nums:
                        if n == year:
                            continue
                        if 1 <= n <= 31:
                            day = n
                            break
                    
                    if day is None and year is not None:
                        day = 1
                    elif day is None:
                        if nums and 1 <= nums[0] <= 31:
                            day = nums[0]
                        else:
                            day = 1
                    
                    if year is None:
                        year = now.year
                    
                    try:
                        dt = datetime(year, m_idx, day, tzinfo=timezone.utc)
                        # If date is in the future, it might be from last year
                        if dt > now and len(digits) == 1:
                            dt = datetime(year - 1, m_idx, day, tzinfo=timezone.utc)
                        return dt.strftime('%Y-%m-%d')
                    except ValueError:
                        pass
    except Exception as e:
        logger.warning(f"Error parsing date string '{text}': {e}")
        
    return ""


def is_recent_post(posted_at_str: str) -> bool:
    """
    Check if a post was published within the last 4 days (today, yesterday, or up to 4 days ago).
    If no date is available, returns True.
    """
    if not posted_at_str:
        return True
    
    try:
        # Standard ISO format: 2026-06-16T14:30:00 or simple date: 2026-06-16
        date_part = posted_at_str.split("T")[0].strip()
        post_date = datetime.strptime(date_part, "%Y-%m-%d").date()
        
        # Get current date in UTC (since all scraper dates are normalized to UTC/local ISO)
        today = datetime.now(timezone.utc).date()
        delta = today - post_date
        
        # Keep if it is 4 days old or newer (or future due to timezone overlap)
        return delta.days <= 4
    except Exception as e:
        logger.warning(f"Error checking date recency for '{posted_at_str}': {e}")
        return True
