import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional


# --- Helper functions (module-level, replacing instance methods) ---

def _get_file_path(data_type: str) -> Path:
    storage_dir = Path(os.environ.get("STORAGE_PATH", "storage"))
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

async def local_memory(
    action: str, 
    data_type: str = "fact", 
    key: str = "", 
    value: str = ""
) -> dict:
    """
    儲存與讀取記憶的工具。支援兩種類型：
    1. 'fact' (長期事實): 用於記錄使用者偏好、姓名、重要人事物。會永久保留。
    2. 'event' (事件紀錄): 用於記錄對話摘要、任務執行結果。會定期自動清理。

    支援的操作(action)：
    - 'set': 儲存記憶 (需提供 data_type, key, value)。
    - 'get': 讀取特定記憶 (需提供 data_type, key)。
    - 'delete': 刪除特定記憶 (需提供 data_type, key)。
    - 'list': 列出所有鍵值 (需提供 data_type)。
    """
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
