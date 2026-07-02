#!/bin/bash
cd /home/bittu/Desktop/ZDCURLCOLEECTORFINAL
nohup venv/bin/python run.py > fastapi.log 2>&1 &
nohup venv/bin/python run_telegram_bot.py > telegram_bot.log 2>&1 &
echo "Services launched successfully in background."
