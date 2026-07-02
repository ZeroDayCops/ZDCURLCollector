# 🚀 ZDCURLCollector

ZDCURLCollector is a FastAPI and Playwright-based social media monitoring system designed for Linux. It scrapes posts from **Instagram, Facebook, LinkedIn, YouTube, and Pinterest**, filters for recency (last 4 days), and broadcasts updates or inactivity warnings directly to a Telegram channel.

---

## ⚡ Linux Quick Start

```bash
# 1. Clone & Enter
git clone https://github.com/ZeroDayCops/ZDCURLCollector.git
cd ZDCURLCollector

# 2. Setup Virtual Environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Requirements & Playwright
pip install -r requirements.txt
playwright install chromium
playwright install-deps

# 4. Start Server
./run_project.sh
```

---

## 📖 Documentation

For detailed configurations, guides, and architecture diagrams:

*   **[Setup & Usage Guide (SETUP.md)](file:///home/bittu/Desktop/ZDCURLCOLEECTORFINAL/SETUP.md)**: Detailed use cases, session cookie capturing instructions, and Apify API configuration.
*   **[Project Architecture (PROJECT.md)](file:///home/bittu/Desktop/ZDCURLCOLEECTORFINAL/PROJECT.md)**: Detailed directory breakdown, code workflows, and system design overview.
