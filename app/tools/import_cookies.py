"""
Cookie Importer Tool
Allows importing cookies from JSON (EditThisCookie, Playwright, etc.) or raw Cookie header strings
and saves them to sessions/<platform>_session.json.

Usage:
    python -m app.tools.import_cookies linkedin "<cookie_data>"
    or pipe cookies via stdin:
    echo '<cookie_data>' | python -m app.tools.import_cookies linkedin
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict

# Map of platforms to their default domains
DOMAINS = {
    "linkedin": ".linkedin.com",
    "facebook": ".facebook.com",
    "instagram": ".instagram.com",
    "pinterest": ".pinterest.com"
}

SESSIONS_DIR = Path("./sessions")

def parse_raw_cookie_string(cookie_str: str, default_domain: str) -> List[Dict]:
    """Parse a raw HTTP Cookie header string into Playwright cookie format."""
    cookies = []
    # Split by semicolon
    parts = cookie_str.strip().split(";")
    for part in parts:
        if not part.strip():
            continue
        if "=" not in part:
            continue
        
        name, val = part.split("=", 1)
        name = name.strip()
        val = val.strip()
        
        cookies.append({
            "name": name,
            "value": val,
            "domain": default_domain,
            "path": "/",
            "expires": -1,
            "httpOnly": False,
            "secure": True,
            "sameSite": "None" if default_domain == ".linkedin.com" else "Lax"
        })
    return cookies

def normalize_json_cookies(cookie_list: List[Dict], default_domain: str) -> List[Dict]:
    """Normalize fields from other JSON formats (like EditThisCookie) to Playwright format."""
    normalized = []
    for c in cookie_list:
        if not isinstance(c, dict) or "name" not in c or "value" not in c:
            continue
            
        # Determine domain
        domain = c.get("domain") or default_domain
        if not domain.startswith(".") and not domain.startswith("http"):
            # Ensure domain starts with dot if it's a domain-level cookie
            if not domain.startswith("www."):
                domain = "." + domain
                
        # Handle expiration date mapping
        expires = c.get("expires")
        if expires is None and "expirationDate" in c:
            expires = c["expirationDate"]
        if expires is None:
            expires = -1
            
        normalized.append({
            "name": c["name"],
            "value": c["value"],
            "domain": domain,
            "path": c.get("path") or "/",
            "expires": float(expires) if expires != -1 else -1,
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", True),
            "sameSite": c.get("sameSite") or ("None" if "linkedin" in domain else "Lax")
        })
    return normalized

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.tools.import_cookies <platform> [cookie_data]")
        print("Platforms: linkedin, facebook, instagram, pinterest")
        sys.exit(1)
        
    platform = sys.argv[1].lower().strip()
    if platform not in DOMAINS:
        print(f"❌ Unsupported platform: {platform}")
        sys.exit(1)
        
    # Read cookie data from args or stdin
    cookie_data = ""
    if len(sys.argv) > 2:
        cookie_data = sys.argv[2]
    else:
        # Check if anything is piped via stdin
        if not sys.stdin.isatty():
            cookie_data = sys.stdin.read()
            
    if not cookie_data.strip():
        print("❌ No cookie data provided. Please pass as argument or pipe via stdin.")
        sys.exit(1)
        
    cookie_data = cookie_data.strip()
    
    # Try parsing as JSON first
    parsed_cookies = []
    is_json = False
    try:
        data = json.loads(cookie_data)
        if isinstance(data, list):
            parsed_cookies = normalize_json_cookies(data, DOMAINS[platform])
            is_json = True
        elif isinstance(data, dict):
            # Maybe single cookie object
            parsed_cookies = normalize_json_cookies([data], DOMAINS[platform])
            is_json = True
    except json.JSONDecodeError:
        pass
        
    # If not JSON, try parsing as raw cookie string
    if not is_json:
        print("Parsing as raw HTTP Cookie string...")
        parsed_cookies = parse_raw_cookie_string(cookie_data, DOMAINS[platform])
        
    if not parsed_cookies:
        print("❌ Could not parse any valid cookies from input.")
        sys.exit(1)
        
    # Save parsed cookies using the standard session manager
    from app.utils.session_manager import save_session
    saved = save_session(platform, parsed_cookies)
    if saved:
        out_path = SESSIONS_DIR / f"{platform}_session.json"
        print(f"✅ Success! Imported {len(parsed_cookies)} cookies for {platform} into {out_path}")
    else:
        print(f"❌ Failed to save cookies.")
        sys.exit(1)

if __name__ == "__main__":
    main()

