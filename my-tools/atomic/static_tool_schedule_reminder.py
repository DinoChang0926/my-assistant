import json
import os
from typing import Optional

from pydantic import BaseModel, Field

# Break reverse dependency on src.config — use environment variable directly
STORAGE_PATH = os.environ.get("SESSION_STORAGE_PATH", "storage")


class ReminderSchedule(BaseModel):
    type: str = Field(
        default="",
        description="排程類型: once, daily, weekly, yearly",
    )
    at: str = Field(
        default="",
        description="單次提醒的時間 (ISO format, e.g. 2026-02-23T09:00:00)",
    )
    time: str = Field(
        default="", description="定時提醒時間 (HH:MM)"
    )
    weekday: int = Field(
        default=-1,
        description="每週提醒的星期 (0=週一, 6=週日)",
    )
    month: int = Field(
        default=0,
        description="每年提醒的月份 (1-12)，用於 yearly 類型",
    )
    day: int = Field(
        default=0,
        description="每年提醒的日期 (1-31)，用於 yearly 類型",
    )
    lead_days: int = Field(
        default=0,
        description="提前幾天提醒 (預設 0 = 當天)，用於 yearly 類型",
    )


async def schedule_reminder(
    action: str,
    name: str = "",
    text: str = "",
    schedule: str = "",
    active: bool = True,
    chat_id: str = "",
) -> dict:
    """
    管理提醒事項 (CRUD)。支援建立、列出、修改、刪除與切換開關項目。
    提醒條目會被存在 local_memory.json 並由背景系統自動掃描與出發 Telegram 通知。

    :param action: 欲執行的操作類型: create, list, update, delete, toggle
    :param name: 提醒條目的唯一名稱 (例如: daily_report)。系統會自動加上 'reminder_' 前綴。
    :param text: 提醒時發送的內容文字。
    :param schedule: 排程設定。yearly 類型支援結婚紀念日、節日等。
    :param active: 是否啟用該提醒。
    :param chat_id: 目標 Telegram Chat ID (若未提供則預設為當前使用者)。
    """
    memory_file = os.path.join(STORAGE_PATH, "local_memory.json")

    # Load existing memory
    memory = {}
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                memory = json.load(f)
        except Exception as e:
            return {"error": f"Failed to read memory file: {e}"}

    if action == "list":
        reminders = {k: v for k, v in memory.items() if k.startswith("reminder_")}
        return {"reminders": reminders}

    if not name:
        return {"error": "Parameter 'name' is required for this action."}

    key = f"reminder_{name.replace('reminder_', '')}"

    if action == "create":
        if key in memory:
            return {"error": f"Reminder '{name}' already exists. Use 'update' instead."}
        data = {
            "text": text or "時間到了！",
            "schedule": (
                json.loads(schedule) if isinstance(schedule, str) and schedule else schedule
            ),
            "active": active if active is not None else True,
            "chat_id": chat_id,
            "last_triggered": None,
        }
        memory[key] = data
        result_msg = f"Reminder '{name}' created successfully."

    elif action == "update":
        if key not in memory:
            return {"error": f"Reminder '{name}' not found."}
        entry = memory[key]
        if text is not None:
            entry["text"] = text
        if schedule:
            entry["schedule"] = json.loads(schedule) if isinstance(schedule, str) else schedule
        if active is not None:
            entry["active"] = active
        if chat_id is not None:
            entry["chat_id"] = chat_id
        result_msg = f"Reminder '{name}' updated successfully."

    elif action == "delete":
        if key in memory:
            del memory[key]
            result_msg = f"Reminder '{name}' deleted."
        else:
            return {"error": f"Reminder '{name}' not found."}

    elif action == "toggle":
        if key not in memory:
            return {"error": f"Reminder '{name}' not found."}
        is_active = (
            active
            if active is not None
            else not memory[key].get("active", True)
        )
        memory[key]["active"] = is_active
        result_msg = f"Reminder '{name}' is now {'enabled' if is_active else 'disabled'}."

    else:
        return {"error": f"Unknown action: {action}"}

    # Save back to disk
    try:
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=4)
        return {"status": "success", "message": result_msg, "key": key}
    except Exception as e:
        return {"error": f"Failed to save memory: {e}"}
