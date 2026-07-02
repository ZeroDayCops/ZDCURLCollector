"""
Wait for a channel message to auto-detect the channel ID.
Run this, then post ANY message in your channel.
"""

import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot, Update

load_dotenv()


async def poll_for_channel():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    bot = Bot(token=token)

    info = await bot.get_me()
    print(f"🤖 Bot: @{info.username}")
    print()
    print("⏳ Waiting for a message in the channel...")
    print("   👉 Please post ANY message in your Telegram channel NOW")
    print()

    # Clear any old updates first
    updates = await bot.get_updates(timeout=1)
    last_id = updates[-1].update_id if updates else 0

    # Check old updates first for channel info
    for u in updates:
        chat = None
        if u.channel_post:
            chat = u.channel_post.chat
        elif u.my_chat_member:
            chat = u.my_chat_member.chat

        if chat and chat.type in ("channel", "supergroup"):
            channel_id = chat.id
            title = chat.title or "Unknown"
            print(f"✅ Found from existing updates!")
            print(f"   📢 Channel: {title}")
            print(f"   🆔 ID: {channel_id}")
            await save_channel_id(channel_id)
            return

    # Poll for new updates (wait up to 2 minutes)
    for attempt in range(24):  # 24 * 5s = 120 seconds
        try:
            updates = await bot.get_updates(
                offset=last_id + 1,
                timeout=5,
                allowed_updates=["channel_post", "my_chat_member", "message"],
            )
        except Exception as e:
            print(f"   retry... ({e})")
            await asyncio.sleep(2)
            continue

        for u in updates:
            last_id = u.update_id
            chat = None

            if u.channel_post:
                chat = u.channel_post.chat
            elif u.my_chat_member:
                chat = u.my_chat_member.chat
            elif u.message and u.message.chat.type in ("channel", "supergroup"):
                chat = u.message.chat

            if chat and chat.type in ("channel", "supergroup"):
                channel_id = chat.id
                title = chat.title or "Unknown"
                print(f"✅ Detected channel!")
                print(f"   📢 Channel: {title}")
                print(f"   🆔 ID: {channel_id}")
                await save_channel_id(channel_id)
                return

        if attempt % 4 == 3:
            remaining = (24 - attempt) * 5
            print(f"   Still waiting... ({remaining}s left). Post a message in the channel!")

    print("❌ Timed out after 2 minutes. No channel message detected.")
    print("   Make sure the bot is admin and has 'Post Messages' permission.")


async def save_channel_id(channel_id):
    """Auto-update .env with the detected channel ID."""
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()

        new_lines = []
        found = False
        for line in lines:
            if line.startswith("TELEGRAM_CHANNEL_ID="):
                new_lines.append(f"TELEGRAM_CHANNEL_ID={channel_id}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"TELEGRAM_CHANNEL_ID={channel_id}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        print()
        print(f"✅ Auto-saved to .env: TELEGRAM_CHANNEL_ID={channel_id}")
        print("   You can now run: python run_telegram_bot.py")
    else:
        print(f"\n⚠️  No .env file found. Manually set: TELEGRAM_CHANNEL_ID={channel_id}")


asyncio.run(poll_for_channel())
