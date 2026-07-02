import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot
from telegram.request import HTTPXRequest

load_dotenv()

async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    proxy = "socks5://92.118.112.32:1082"
    
    print(f"Testing Telegram with proxy: {proxy}")
    request_client = HTTPXRequest(proxy=proxy)
    bot = Bot(token=token, request=request_client)
    
    async with bot:
        info = await bot.get_me()
        print(f"✅ Connection successful! Bot username: @{info.username}")

if __name__ == "__main__":
    asyncio.run(main())
