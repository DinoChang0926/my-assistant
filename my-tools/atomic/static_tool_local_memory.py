import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from copilot.tools import define_tool
from pydantic import BaseModel, Field


# --- Helper functions (module-level, replacing instance methods) ---

def _get_file_path(data_type: str) -> Path:
    storage_dir = Path("storage")
    storage_dir.mkdir(exist_ok=True)
    filename = "local_memory.json" if data_type == "fact" else "event_log.json"
    return storage_dir / filename


def _load_data(data_type: str):
    path = _get_file_path(data_type)
    if not path.exists():
        return {} if data_type == "fact" else []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {} if data_type == "fact" else []


def _save_data(data_type: str, data):
    path = _get_file_path(data_type)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving {data_type} data: {e}")


def _cleanup_event_log(logs: list) -> list:
    """Cleanup logic: max 50 entries and max 7 days old."""
    now = datetime.now()
    threshold = now - timedelta(days=7)

    filtered = []
    for entry in logs:
        try:
            ts_str = entry.get("timestamp")
            if ts_str:
                ts = datetime.fromisoformat(ts_str)
                if ts > threshold:
                    filtered.append(entry)
        except Exception:
            filtered.append(entry)

    return filtered[-50:]


# --- Tool definition ---

class LocalMemoryParams(BaseModel):
    action: str = Field(
        description="要執行的操作：set(儲存), get(讀取), delete(刪除), list(列出所有鍵值)"
    )
    data_type: str = Field(
        default="fact",
        description=(
            "資料類型：'fact' (長期事實，存於 local_memory.json) "
            "或 'event' (事件紀錄，存於 event_log.json)"
        ),
    )
    key: Optional[str] = Field(
        default=None,
        description="記憶的鍵值 (例如：'user_name', 'session_summary')。",
    )
    value: Optional[str] = Field(
        default=None,
        description="記憶的具體內容。僅在 action 為 'set' 時需要。",
    )


@define_tool(
    description=(
        "儲存與讀取記憶的工具。支援兩種類型：\n"
        "1. 'fact' (長期事實): 用於記錄使用者偏好、姓名、重要人事物。會永久保留。\n"
        "2. 'event' (事件紀錄): 用於記錄對話摘要、任務執行結果。會定期自動清理。\n\n"
        "支援的操作(action)：\n"
        "- 'set': 儲存記憶 (需提供 data_type, key, value)。\n"
        "- 'get': 讀取特定記憶 (需提供 data_type, key)。\n"
        "- 'delete': 刪除特定記憶 (需提供 data_type, key)。\n"
        "- 'list': 列出所有鍵值 (需提供 data_type)。"
    )
)
async def local_memory(params: LocalMemoryParams) -> dict:
    action = params.action
    data_type = params.data_type
    key = params.key
    value = params.value

    if not action:
        return {"status": "error", "message": "Missing 'action' parameter."}

    data = _load_data(data_type)

    if action == "list":
        if data_type == "fact":
            keys = list(data.keys())
        else:
            keys = [entry.get("key") for entry in data]
        return {"status": "success", "data_type": data_type, "keys": keys}

    if not key:
        return {"status": "error", "message": f"Action '{action}' requires a 'key'."}

    if action == "set":
        if value is None:
            return {"status": "error", "message": "Action 'set' requires a 'value'."}

        if data_type == "fact":
            data[key] = value
        else:
            new_entry = {
                "timestamp": datetime.now().isoformat(),
                "key": key,
                "value": value,
            }
            data.append(new_entry)
            data = _cleanup_event_log(data)

        _save_data(data_type, data)
        return {"status": "success", "message": f"Saved as {data_type}.", "key": key}

    elif action == "get":
        if data_type == "fact":
            if key in data:
                return {"status": "success", "value": data[key]}
        else:
            for entry in reversed(data):
                if entry.get("key") == key:
                    return {
                        "status": "success",
                        "value": entry.get("value"),
                        "timestamp": entry.get("timestamp"),
                    }

        return {"status": "not_found", "message": f"'{key}' not found in {data_type}."}

    elif action == "delete":
        if data_type == "fact":
            if key in data:
                del data[key]
                _save_data(data_type, data)
                return {"status": "success", "message": f"Deleted {key} from facts."}
        else:
            initial_len = len(data)
            data = [e for e in data if e.get("key") != key]
            if len(data) < initial_len:
                _save_data(data_type, data)
                return {
                    "status": "success",
                    "message": f"Deleted all {key} entries from events.",
                }

        return {"status": "not_found", "message": "Nothing to delete."}

    return {"status": "error", "message": f"Unknown action '{action}'."}


# --- Module exports for registry discovery (Phase 3a convention) ---
EXPORTED_TOOLS = [local_memory]
TOOL_CATEGORY = "memory"
