# ⚙️ ZDCURLCollector Setup & Usage Guide

This guide provides deep technical instructions, system use cases, session cookie capturing guidelines, and information on the Apify API integration.

---

## 🎯 Use Cases

ZDCURLCollector is designed for brand-monitoring and social intelligence teams:
1. **Brand Feed Tracking**: Monitor official handles of brands/competitors on Instagram, Facebook, LinkedIn, YouTube, and Pinterest.
2. **Recency Monitoring**: Extract and filter posts published within the last 4 days (recency threshold).
3. **Telegram Channel Sync**: Automatically format and forward posts to a Telegram channel.
4. **Inactive Alerts**: Notify the Telegram channel with a warning if a brand has not posted for 4 days.
5. **Deduplication Safeguard**: Keep record of sent URLs in a transactional database (`data/sent_posts.json`) to prevent forwarding the same post twice.
6. **Bulk Scrapes**: Upload Excel or TXT lists of profiles via the dark glassmorphic FastAPI Web UI, running tasks in background loops.

---

## 💻 Detailed Linux Setup

This project is optimized to run on **Linux** (Ubuntu/Debian recommended). Follow these steps to prepare your environment.

### 1. Clone & Navigate
Ensure the code is placed in your target directory:
```bash
git clone https://github.com/ZeroDayCops/ZDCURLCollector.git
cd ZDCURLCollector
```

### 2. Configure Virtual Environment (venv)
Use a clean virtual environment to avoid dependency conflicts:
```bash
# Create venv
python3 -m venv venv

# Activate venv
source venv/bin/activate
```

### 3. Install Python Dependencies
```bash
# Upgrade pip to latest
pip install --upgrade pip

# Install project packages
pip install -r requirements.txt
```

### 4. Install Playwright Browsers & Linux System Packages
Playwright requires browser binaries and system-level libraries to run Chromium in headless mode:
```bash
# Install Chromium browser binary
playwright install chromium

# Install system library dependencies (requires sudo)
playwright install-deps
```

---

## 🔑 Session Cookie Capture (Session Adding)

Facebook, Instagram, and LinkedIn require logged-in sessions to scrape content reliably and avoid login redirections.

### How to Add & Save Sessions
1. **Make scripts executable**:
   ```bash
   chmod +x login_helper.sh check_sessions.sh
   ```
2. **Run the login helper** for your target platform:
   ```bash
   ./login_helper.sh instagram
   # OR: ./login_helper.sh facebook
   # OR: ./login_helper.sh linkedin
   ```
3. **Log in manually**:
   - An interactive Chromium browser window will open.
   - Enter your login credentials, complete 2FA, and navigate to the home feed.
4. **Save session**:
   - Go back to your terminal window.
   - Press **Enter**. The helper script will extract cookies and save them to `sessions/<platform>_session.json`.

### Audit Session Health
Run the check script regularly to ensure sessions are active and have not been invalidated:
```bash
./check_sessions.sh
```

---

## 🔌 Apify API Integration

ZDCURLCollector integrates with the **Apify API** as a highly reliable scraping mechanism for Facebook and Instagram.

### 1. Configure the Apify Token
Add your Apify API Token to the `.env` file in the root directory:
```ini
APIFY_TOKEN=your_apify_api_token_here
```
*(If no token is supplied in `.env`, the scraper falls back to a default API token).*

### 2. Scraper Execution Flow
- **Facebook Scraper (`app/scrapers/facebook.py`)**:
  - Tries to execute using the `apify~facebook-posts-scraper` actor.
  - Automatically loads the targeted Facebook URL and pulls the latest posts.
  - **Fallback**: If Apify fails (token limits, network timeout, error), the scraper automatically falls back to local Playwright desktop automation, which logs in using the saved `sessions/facebook_session.json` cookies.
- **Instagram Scraper**:
  - The core codebase runs Instagram scraping locally via Playwright.
  - There is a scratch test script (`scratch/test_apify.py`) demonstrating how to leverage the `apify~instagram-post-scraper` actor to fetch posts.

### 3. Running Apify Scratch Tests
Verify your Apify credentials and scraper responses directly via the CLI:
```bash
# Test Instagram Apify Scraper
python scratch/test_apify.py

# Test Facebook Apify Scraper
python scratch/test_apify_fb.py
```
These tests fetch the latest 3 posts from target profiles (`zuck` on Facebook, `trendsofindia_` on Instagram) and print the URLs, captions, and publication timestamps to the console.
