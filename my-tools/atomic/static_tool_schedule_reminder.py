import json
import os
from typing import Optional

from copilot.tools import define_tool
from pydantic import BaseModel, Field

# Break reverse dependency on src.config — use environment variable directly
STORAGE_PATH = os.environ.get("SESSION_STORAGE_PATH", "storage")


class ReminderSchedule(BaseModel):
    type: Optional[str] = Field(
        default=None,
        description="排程類型: once, daily, weekly, yearly",
    )
    at: Optional[str] = Field(
        default=None,
        description="單次提醒的時間 (ISO format, e.g. 2026-02-23T09:00:00)",
    )
    time: Optional[str] = Field(
        default=None, description="定時提醒時間 (HH:MM)"
    )
    weekday: Optional[int] = Field(
        default=None,
        description="每週提醒的星期 (0=週一, 6=週日)",
    )
    month: Optional[int] = Field(
        default=None,
        description="每年提醒的月份 (1-12)，用於 yearly 類型",
    )
    day: Optional[int] = Field(
        default=None,
        description="每年提醒的日期 (1-31)，用於 yearly 類型",
    )
    lead_days: Optional[int] = Field(
        default=None,
        description="提前幾天提醒 (預設 0 = 當天)，用於 yearly 類型",
    )


class ScheduleReminderParams(BaseModel):
    action: str = Field(
        description="欲執行的操作類型: create, list, update, delete, toggle"
    )
    name: Optional[str] = Field(
        default=None,
        description="提醒條目的唯一名稱 (例如: daily_report)。系統會自動加上 'reminder_' 前綴。",
    )
    text: Optional[str] = Field(
        default=None, description="提醒時發送的內容文字。"
    )
    schedule: Optional[ReminderSchedule] = Field(
        default=None,
        description=(
            "排程設定。yearly 類型支援結婚紀念日、節日 (情人節/七夕等)，"
            "可搭配 lead_days 提前指定天數提醒。"
        ),
    )
    active: Optional[bool] = Field(
        default=None, description="是否啟用該提醒。"
    )
    chat_id: Optional[str] = Field(
        default=None,
        description="目標 Telegram Chat ID (例如: 'telegram_6673258916'，若未提供則預設為當前 session 的使用者)。",
    )


@define_tool(
    description=(
        "管理提醒事項 (CRUD)。支援建立、列出、修改、刪除與切換開關項目。\n"
        "提醒條目會被存在 local_memory.json 並由背景系統自動掃描與出發 Telegram 通知。"
    )
)
async def schedule_reminder(params: ScheduleReminderParams) -> dict:
    memory_file = os.path.join(STORAGE_PATH, "local_memory.json")

    # Load existing memory
    memory = {}
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                memory = json.load(f)
        except Exception as e:
            return {"error": f"Failed to read memory file: {e}"}

    action = params.action

    if action == "list":
        reminders = {k: v for k, v in memory.items() if k.startswith("reminder_")}
        return {"reminders": reminders}

    if not params.name:
        return {"error": "Parameter 'name' is required for this action."}

    name = params.name
    key = f"reminder_{name.replace('reminder_', '')}"

    if action == "create":
        if key in memory:
            return {"error": f"Reminder '{name}' already exists. Use 'update' instead."}
        data = {
            "text": params.text or "時間到了！",
            "schedule": (
                params.schedule.model_dump(exclude_none=True) if params.schedule else {}
            ),
            "active": params.active if params.active is not None else True,
            "chat_id": params.chat_id,
            "last_triggered": None,
        }
        memory[key] = data
        result_msg = f"Reminder '{name}' created successfully."

    elif action == "update":
        if key not in memory:
            return {"error": f"Reminder '{name}' not found."}
        entry = memory[key]
        if params.text is not None:
            entry["text"] = params.text
        if params.schedule is not None:
            entry["schedule"] = params.schedule.model_dump(exclude_none=True)
        if params.active is not None:
            entry["active"] = params.active
        if params.chat_id is not None:
            entry["chat_id"] = params.chat_id
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
        active = (
            params.active
            if params.active is not None
            else not memory[key].get("active", True)
        )
        memory[key]["active"] = active
        result_msg = f"Reminder '{name}' is now {'enabled' if active else 'disabled'}."

    else:
        return {"error": f"Unknown action: {action}"}

    # Save back to disk
    try:
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=4)
        return {"status": "success", "message": result_msg, "key": key}
    except Exception as e:
        return {"error": f"Failed to save memory: {e}"}


# --- Module exports for registry discovery (Phase 3a convention) ---
EXPORTED_TOOLS = [schedule_reminder]
TOOL_CATEGORY = "system"
