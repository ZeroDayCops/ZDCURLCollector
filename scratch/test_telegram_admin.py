import asyncio
import os
import logging
from dotenv import load_dotenv

# Load env
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)

from app.telegram_bot.bot import send_admin_message

async def main():
    print("Sending test 'Hi' message to admin...")
    admin_id = os.getenv("TELEGRAM_ADMIN_USER_ID")
    print(f"Target Admin User ID: {admin_id}")
    
    try:
        await send_admin_message("👋 Hi! This is a test message from your ZDC URL Collector Bot.")
        print("Success! Message sent successfully.")
    except Exception as e:
        print(f"Failure sending message: {e}")

if __name__ == "__main__":
    asyncio.run(main())
