from src.config import settings
import os
from dotenv import load_dotenv

load_dotenv()

print(f"Environment REMOTE_TOKEN: {os.getenv('TELEGRAM_BOT_TOKEN')}")
print(f"Settings TOKEN: {settings.TELEGRAM_BOT_TOKEN}")

if settings.TELEGRAM_BOT_TOKEN:
    print("Token is SET in settings.")
else:
    print("Token is NONE/EMPTY in settings.")
