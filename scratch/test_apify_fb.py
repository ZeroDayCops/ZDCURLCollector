import urllib.request
import urllib.error
import json
import os
from dotenv import load_dotenv

load_dotenv()

def test_apify_fb():
    token = os.getenv("APIFY_TOKEN", "").strip() or "YOUR_APIFY_TOKEN_HERE"
    if token == "YOUR_APIFY_TOKEN_HERE" or not token:
        print("❌ Error: APIFY_TOKEN is not set in environment or .env file.")
        return
    fb_url = "https://www.facebook.com/zuck"
    
    url = f"https://api.apify.com/v2/acts/apify~facebook-posts-scraper/run-sync-get-dataset-items?token={token}"
    
    payload = {
        "startUrls": [{"url": fb_url}],
        "resultsLimit": 3,
        "viewOption": "posts"
    }
    
    data_bytes = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={'Content-Type': 'application/json'}
    )
    
    print(f"🚀 Running Apify Facebook Scraper for '{fb_url}'...")
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            status_code = response.getcode()
            print(f"Status Code: {status_code}")
            
            res_body = response.read().decode('utf-8')
            data = json.loads(res_body)
            
            print(f"✅ Success! Found {len(data)} items:")
            for idx, item in enumerate(data, 1):
                post_url = item.get("url") or item.get("postUrl")
                caption = item.get("text", "")[:60] or item.get("caption", "")[:60]
                posted_at = item.get("time") or item.get("date")
                print(f"  [{idx}] URL: {post_url}")
                print(f"      Text: {caption}")
                print(f"      Time: {posted_at}")
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP Error {e.code}: {e.read().decode('utf-8', errors='ignore')}")
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    test_apify_fb()
