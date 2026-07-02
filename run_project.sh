#!/bin/bash

# Exit on error
set -e

# Change directory to the script's actual directory so it runs correctly from anywhere
cd "$(dirname "$(readlink -f "$0")")"

echo "===================================================="
echo "🚀 ZDCURLCollector All-in-One Setup & Runner"
echo "===================================================="

# 1. Setup Virtual Environment
if [ ! -d "venv" ] || [ ! -f "venv/bin/pip" ] || ! ./venv/bin/python -c "import sys" 2>/dev/null; then
    echo "📦 Re-creating/Creating virtual environment..."
    rm -rf venv
    python3 -m venv venv
else
    echo "✅ Virtual environment already exists and is healthy."
fi

# Use explicit virtual environment python binary path
VENV_PYTHON="./venv/bin/python"

# 2. Install requirements
echo "📥 Installing/Updating Python requirements..."
$VENV_PYTHON -m pip install --upgrade pip
$VENV_PYTHON -m pip install -r requirements.txt

# 3. Install Playwright browser
echo "🎭 Installing Playwright Chromium browser..."
$VENV_PYTHON -m playwright install chromium

# 4. Check or download ngrok locally
NGROK_BIN="ngrok"
if ! command -v ngrok &> /dev/null; then
    if [ -f "./ngrok" ]; then
        NGROK_BIN="./ngrok"
        echo "✅ Found local ngrok binary."
    else
        echo "🔍 ngrok not found globally. Attempting to download it locally..."
        if command -v wget &> /dev/null; then
            wget -q https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz -O ngrok.tgz
            tar -xzf ngrok.tgz
            rm ngrok.tgz
            NGROK_BIN="./ngrok"
            echo "✅ ngrok downloaded locally."
        elif command -v curl &> /dev/null; then
            curl -sSL https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz -o ngrok.tgz
            tar -xzf ngrok.tgz
            rm ngrok.tgz
            NGROK_BIN="./ngrok"
            echo "✅ ngrok downloaded locally."
        else
            echo "⚠️ Neither wget nor curl found. Please install ngrok manually."
        fi
    fi
else
    echo "✅ ngrok is installed globally."
fi

# Check for .env file
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "📝 Creating .env from .env.example..."
        cp .env.example .env
        echo "⚠️  Please update your .env file with your Telegram Bot Token and Channel ID!"
    else
        echo "❌ No .env or .env.example found!"
    fi
fi

# Clean up any existing process on port 8000, bot instances, and ngrok tunnels
echo "🧹 Checking for existing processes on port 8000..."
if command -v fuser &> /dev/null; then
    fuser -k 8000/tcp || true
fi
echo "🧹 Killing any orphaned Telegram Bot scheduler processes..."
pkill -f run_telegram_bot.py || true
echo "🧹 Killing any orphaned ngrok tunnel processes..."
pkill -f ngrok || true

# Function to stop all background processes on Ctrl+C
cleanup() {
    echo -e "\n🛑 Stopping all services..."
    # Kill background jobs
    jobs -p | xargs -r kill 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "===================================================="
echo "⚡ Starting FastAPI Server, Telegram Bot, and ngrok..."
echo "===================================================="

# Start FastAPI server
echo "📡 Starting FastAPI server..."
$VENV_PYTHON run.py > fastapi.log 2>&1 &
API_PID=$!

# Start Telegram Bot
echo "🤖 Starting Telegram Bot scheduler..."
$VENV_PYTHON run_telegram_bot.py > telegram_bot.log 2>&1 &
BOT_PID=$!

# Wait a moment for server to start
sleep 3

# Start ngrok
if [ "$NGROK_BIN" = "./ngrok" ] || command -v ngrok &> /dev/null; then
    echo "🔗 Starting ngrok tunnel..."
    echo "----------------------------------------------------"
    echo "👉 Press CTRL+C to stop all services (FastAPI, Bot, ngrok)"
    echo "👉 FastAPI logs: tail -f fastapi.log"
    echo "👉 Telegram Bot logs: tail -f telegram_bot.log"
    echo "----------------------------------------------------"
    
    # Run ngrok in the foreground so the user sees the ngrok UI/URL
    $NGROK_BIN http 8000
else
    echo "⚠️ Cannot start ngrok automatically (not installed or downloaded)."
    echo "👉 FastAPI and Telegram Bot are running in the background."
    echo "👉 Press CTRL+C to stop them."
    # Wait for background jobs to finish
    wait
fi
