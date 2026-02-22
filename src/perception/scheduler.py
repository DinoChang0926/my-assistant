import asyncio
import json
import os
import logging
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional

from src.config import settings
from src.perception.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)

class SchedulerService:
    """
    Background service that periodically checks local_memory.json for active reminders
    and dispatches them via Telegram.
    """

    def __init__(self, bot: TelegramBot):
        self.bot = bot
        self.storage_path = Path(settings.SESSION_STORAGE_PATH)
        self.memory_file = self.storage_path / "local_memory.json"
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background scheduler loop."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("SchedulerService started.")

    async def stop(self):
        """Stop the background scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SchedulerService stopped.")

    async def _loop(self):
        """Main check loop, runs every 60 seconds."""
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Error in SchedulerService tick: {e}", exc_info=True)
            
            # Sleep until the start of the next minute for precision
            now = datetime.now()
            sleep_seconds = 60 - now.second
            await asyncio.sleep(sleep_seconds)

    async def _tick(self):
        """Check all active reminders in local_memory.json."""
        if not self.memory_file.exists():
            return

        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                memory = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read memory file for scheduler: {e}")
            return

        now = datetime.now()
        updated = False
        
        # Reminders are stored with "reminder_" prefix
        for key, data in memory.items():
            if not key.startswith("reminder_") or not isinstance(data, dict):
                continue
            
            if not data.get("active", True):
                continue
            
            if self._should_trigger(data, now):
                await self._trigger(key, data)
                data["last_triggered"] = now.isoformat()
                
                # Auto-disable single reminders
                if data.get("schedule", {}).get("type") == "once":
                    data["active"] = False
                    
                updated = True

        if updated:
            try:
                with open(self.memory_file, 'w', encoding='utf-8') as f:
                    json.dump(memory, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.error(f"Failed to save updated memory after scheduler tick: {e}")

    def _should_trigger(self, data: dict, now: datetime) -> bool:
        """Determines if a reminder should trigger based on its schedule."""
        schedule = data.get("schedule", {})
        sched_type = schedule.get("type")
        last_triggered_str = data.get("last_triggered")
        last_triggered = datetime.fromisoformat(last_triggered_str) if last_triggered_str else None

        if sched_type == "once":
            at_str = schedule.get("at")
            if not at_str:
                return False
            at_dt = datetime.fromisoformat(at_str)
            # If time has passed and we haven't triggered it yet
            return now >= at_dt and last_triggered is None

        if sched_type == "daily":
            target_time_str = schedule.get("time") # HH:MM
            if not target_time_str:
                return False
            
            h, m = map(int, target_time_str.split(":"))
            target_time = time(h, m)
            
            # Is it time yet today?
            current_target = datetime.combine(now.date(), target_time)
            
            # If it's currently at or after target time, and we haven't triggered it TODAY
            if now >= current_target:
                if not last_triggered or last_triggered.date() < now.date():
                    return True
            return False

        if sched_type == "weekly":
            weekday = schedule.get("weekday") # 0-6
            target_time_str = schedule.get("time")
            if weekday is None or not target_time_str:
                return False
            
            if now.weekday() != weekday:
                return False
                
            h, m = map(int, target_time_str.split(":"))
            target_time = time(h, m)
            current_target = datetime.combine(now.date(), target_time)
            
            if now >= current_target:
                 if not last_triggered or last_triggered.date() < now.date():
                    return True
            return False

        if sched_type == "yearly":
            month = schedule.get("month")
            day = schedule.get("day")
            target_time_str = schedule.get("time", "09:00")
            lead_days = int(schedule.get("lead_days", 0))
            if not month or not day:
                return False
            
            h, m = map(int, target_time_str.split(":"))
            target_time = time(h, m)
            
            # Find next trigger date for this year or next year
            from datetime import timedelta as td
            try:
                event_date = datetime(now.year, month, day)
            except ValueError:
                return False  # Invalid date (e.g. Feb 30)
            
            trigger_date = event_date - td(days=lead_days)
            current_target = datetime.combine(trigger_date.date(), target_time)
            
            # If this year's trigger already passed, check next year
            if now.date() > trigger_date.date():
                try:
                    event_date_next = datetime(now.year + 1, month, day)
                except ValueError:
                    return False
                trigger_date = event_date_next - td(days=lead_days)
                current_target = datetime.combine(trigger_date.date(), target_time)
            
            if now.date() == trigger_date.date() and now >= current_target:
                if not last_triggered or last_triggered.date() < now.date():
                    return True
            return False

        return False

    async def _trigger(self, key: str, data: dict):
        """Sends the reminder message via Telegram."""
        text = data.get("text", "時間到了！")
        chat_id_pref = data.get("chat_id") # e.g. "telegram_123456"
        
        chat_id = None
        if chat_id_pref and chat_id_pref.startswith("telegram_"):
            try:
                chat_id = int(chat_id_pref.replace("telegram_", ""))
            except ValueError:
                pass
        
        if not chat_id:
            logger.warning(f"No valid chat_id found for reminder {key}: {chat_id_pref}")
            return

        logger.info(f"Triggering reminder {key} for chat_id {chat_id}")
        
        try:
            # Access the bot instance from the wrapper
            if self.bot and self.bot.app:
                await self.bot.app.bot.send_message(
                    chat_id=chat_id,
                    text=f"⏰ **提醒時間到！**\n\n{text}",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Failed to send Telegram reminder {key}: {e}")
