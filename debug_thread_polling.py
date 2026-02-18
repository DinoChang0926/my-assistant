import threading
import time
import os
import asyncio
from telegram.ext import ApplicationBuilder
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def run_bot(token):
    print(f"Thread started. Token: {token[:5]}...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app = ApplicationBuilder().token(token).build()
    print("App built. Starting polling...")
    app.run_polling(stop_signals=None)
    print("Polling stopped (unexpected if not signaled).")
    loop.close()

if __name__ == "__main__":
    if not TOKEN:
        print("No token.")
        exit(1)
        
    t = threading.Thread(target=run_bot, args=(TOKEN,), daemon=True)
    t.start()
    
    print("Main thread sleeping...")
    time.sleep(10)
    print("Main thread exit.")
