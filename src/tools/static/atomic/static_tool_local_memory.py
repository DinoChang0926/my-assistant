import os
import json
from pathlib import Path
from pydantic import Field
from src.tools.base import BaseTool

class LocalMemoryTool(BaseTool):
    """
    Tool to store and retrieve long-term memory locally in a JSON file.
    Use this to remember user preferences, important facts, or context across sessions.
    """
    
    name: str = "local_memory"
    description: str = (
        "儲存與讀取長期記憶的工具。當使用者要求你「記住」某件事，或你需要記錄跨對話的偏好設定時使用。\n"
        "支援的操作(action)：\n"
        "- 'set': 儲存或更新記憶 (需要 key 與 value)。\n"
        "- 'get': 讀取特定記憶 (需要 key)。\n"
        "- 'delete': 刪除特定記憶 (需要 key)。\n"
        "- 'list': 列出所有已記憶的主題鍵值 (不需 key 與 value)。"
    )
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["set", "get", "delete", "list"],
                    "description": "要執行的操作：set(儲存), get(讀取), delete(刪除), list(列出所有鍵值)"
                },
                "key": {
                    "type": "string",
                    "description": "記憶的主題或鍵值 (例如：'user_name', 'favorite_food')。list 操作不需提供。"
                },
                "value": {
                    "type": "string",
                    "description": "記憶的具體內容。僅在 action 為 'set' 時需要提供。"
                }
            },
            "required": ["action"]
        }

    def _get_memory_file(self) -> Path:
        """Returns the path to the local memory JSON file."""
        # Ensure the path aligns with the project's storage directory
        storage_dir = Path("storage")
        storage_dir.mkdir(exist_ok=True)
        return storage_dir / "local_memory.json"

    def _load_memory(self) -> dict:
        """Loads the memory from the JSON file."""
        mem_file = self._get_memory_file()
        if not mem_file.exists():
            return {}
        
        try:
            with open(mem_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            # If file is corrupted, return empty dictionary
            return {}
        except Exception as e:
            print(f"Error loading memory: {e}")
            return {}

    def _save_memory(self, memory_data: dict):
        """Saves the memory data to the JSON file."""
        mem_file = self._get_memory_file()
        try:
            with open(mem_file, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving memory: {e}")

    async def execute(self, **kwargs) -> dict:
        action = kwargs.get("action")
        key = kwargs.get("key")
        value = kwargs.get("value")

        if not action:
            return {"status": "error", "message": "Missing 'action' parameter."}

        memory_data = self._load_memory()

        if action == "list":
            keys = list(memory_data.keys())
            return {
                "status": "success",
                "message": f"Found {len(keys)} memories.",
                "keys": keys
            }

        if not key:
             return {"status": "error", "message": f"Action '{action}' requires a 'key' parameter."}

        if action == "set":
            if value is None:
                 return {"status": "error", "message": "Action 'set' requires a 'value' parameter."}
            memory_data[key] = value
            self._save_memory(memory_data)
            return {"status": "success", "message": f"Memory '{key}' saved successfully.", "key": key, "value": value}

        elif action == "get":
            if key in memory_data:
                return {"status": "success", "key": key, "value": memory_data[key]}
            else:
                return {"status": "not_found", "message": f"Memory '{key}' not found."}

        elif action == "delete":
            if key in memory_data:
                del memory_data[key]
                self._save_memory(memory_data)
                return {"status": "success", "message": f"Memory '{key}' deleted successfully."}
            else:
                 return {"status": "not_found", "message": f"Memory '{key}' not found, nothing to delete."}

        else:
            return {"status": "error", "message": f"Unknown action '{action}'."}
