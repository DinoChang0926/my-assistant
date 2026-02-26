import json
import os
from typing import Any, Dict, List, Optional
from src.tools.base import BaseTool
from src.config import settings  # TODO: Phase 2 — 移除對 src.config 的直接依賴，改為參數注入或環境變數

class ScheduleReminderTool(BaseTool):
    """
    Tool for managing periodic reminders (CRUD).
    Reminders are stored in local_memory.json with a 'reminder_' prefix.
    """

    @property
    def name(self) -> str:
        return "schedule_reminder"

    @property
    def category(self) -> str:
        return "system"

    @property
    def description(self) -> str:
        return (
            "管理提醒事項 (CRUD)。支援建立、列出、修改、刪除與切換開關項目。\n"
            "提醒條目會被存在 local_memory.json 並由背景系統自動掃描與出發 Telegram 通知。"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "update", "delete", "toggle"],
                    "description": "欲執行的操作類型。"
                },
                "name": {
                    "type": "string",
                    "description": "提醒條目的唯一名稱 (例如: daily_report)。系統會自動加上 'reminder_' 前綴。"
                },
                "text": {
                    "type": "string",
                    "description": "提醒時發送的內容文字。"
                },
                "schedule": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["once", "daily", "weekly", "yearly"]},
                        "at": {"type": "string", "description": "單次提醒的時間 (ISO format, e.g. 2026-02-23T09:00:00)"},
                        "time": {"type": "string", "description": "定時提醒時間 (HH:MM)"},
                        "weekday": {"type": "integer", "description": "每週提醒的星期 (0=週一, 6=週日)"},
                        "month": {"type": "integer", "description": "每年提醒的月份 (1-12)，用於 yearly 類型"},
                        "day": {"type": "integer", "description": "每年提醒的日期 (1-31)，用於 yearly 類型"},
                        "lead_days": {"type": "integer", "description": "提前幾天提醒 (預設 0 = 當天)，用於 yearly 類型。例如情人節提前 30 天提醒則設為 30"}
                    },
                    "description": "排程設定。yearly 類型支援結婚紀念日、節日 (情人節/七夕等)，可搭配 lead_days 提前指定天數提醒。"
                },
                "active": {
                    "type": "boolean",
                    "description": "是否啟用該提醒。"
                },
                "chat_id": {
                    "type": "string",
                    "description": "目標 Telegram Chat ID (例如: 'telegram_6673258916'，若未提供則預設為當前 session 的使用者)。"
                }
            },
            "required": ["action"]
        }

    async def execute(self, action: str, name: Optional[str] = None, **kwargs) -> dict:
        storage_path = settings.SESSION_STORAGE_PATH
        memory_file = os.path.join(storage_path, "local_memory.json")
        
        # Load existing memory
        memory = {}
        if os.path.exists(memory_file):
            try:
                with open(memory_file, 'r', encoding='utf-8') as f:
                    memory = json.load(f)
            except Exception as e:
                return {"error": f"Failed to read memory file: {e}"}

        # Handle actions
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
                "text": kwargs.get("text", "時間到了！"),
                "schedule": kwargs.get("schedule", {}),
                "active": kwargs.get("active", True),
                "chat_id": kwargs.get("chat_id"),
                "last_triggered": None
            }
            memory[key] = data
            result_msg = f"Reminder '{name}' created successfully."

        elif action == "update":
            if key not in memory:
                return {"error": f"Reminder '{name}' not found."}
            
            # Merge updates
            entry = memory[key]
            if "text" in kwargs: entry["text"] = kwargs["text"]
            if "schedule" in kwargs: entry["schedule"] = kwargs["schedule"]
            if "active" in kwargs: entry["active"] = kwargs["active"]
            if "chat_id" in kwargs: entry["chat_id"] = kwargs["chat_id"]
            
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
            active = kwargs.get("active", not memory[key].get("active", True))
            memory[key]["active"] = active
            result_msg = f"Reminder '{name}' is now {'enabled' if active else 'disabled'}."

        else:
            return {"error": f"Unknown action: {action}"}

        # Save back to disk
        try:
            with open(memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory, f, ensure_ascii=False, indent=4)
            return {"status": "success", "message": result_msg, "key": key}
        except Exception as e:
            return {"error": f"Failed to save memory: {e}"}
