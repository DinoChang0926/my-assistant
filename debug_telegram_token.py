import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot

# Load env
load_dotenv()

async def check_token():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    print(f"Checking Token: {token[:10]}... (Total len: {len(token) if token else 0})")
    
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not found in environment.")
        return

    try:
        bot = Bot(token=token)
        me = await bot.get_me()
        print(f"\n✅ SUCCESS!")
        print(f"Bot Name: {me.first_name}")
        print(f"Username: @{me.username}")
        print(f"ID: {me.id}")
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        print("Please check if the token is correct.")

if __name__ == "__main__":
    asyncio.run(check_token())
