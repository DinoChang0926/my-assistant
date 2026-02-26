import sys
import subprocess
import asyncio
from pathlib import Path
from src.tools.base import BaseTool
from src.tools.static.code_validator import validate_tool_code

class CreateToolTool(BaseTool):
    """
    A tool that allows the Agent to create new tool Python files.
    Includes comprehensive safety validation.
    """

    def __init__(self, registry=None):
        """
        Args:
            registry: ToolRegistry instance (Dependency Injection)
        """
        self.registry = registry
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "create_tool"

    @property
    def category(self) -> str:
        return "system"

    @property
    def description(self) -> str:
        return "建立新的 Python 技能。目前僅限使用預裝庫 (pandas, yfinance, requests 等)。會自動進行安全檢查並熱重載。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "技能名稱 (e.g., 'crypto_price_checker')。"
                },
                "category": {
                    "type": "string",
                    "description": "技能分類 (e.g., 'finance', 'github', 'system')，預設為 'general'。"
                },
                "description": {
                    "type": "string",
                    "description": "技能的詳細描述。"
                },
                "tool_parameters": {
                    "type": "object",
                    "description": "技能的 JSON Schema 參數定義 (必須包含 type: object 及 properties)。"
                },
                "code_content": {
                    "type": "string",
                    "description": (
                        "完整的 Python CLI 腳本程式碼。\n"
                        "⚠️ 必須實作為獨立執行的腳本，不需繼承 `BaseTool`。\n"
                        "⚠️ 必須透過 `sys.stdin.read()` 接收 JSON 格式的參數。\n"
                        "⚠️ 必須將執行結果以單一 JSON 格式透過 `print()` (stdout) 輸出。任何日誌或錯誤都必須輸出至 stderr (`sys.stderr.write`)。\n"
                        "💡 [程式碼骨架]:\n"
                        "import sys, json\n"
                        "def main():\n"
                        "    try:\n"
                        "        args = json.loads(sys.stdin.read() or '{}')\n"
                        "        result = {'status': 'success', 'data': args}\n"
                        "        print(json.dumps(result))\n"
                        "    except Exception as e:\n"
                        "        print(json.dumps({'status': 'error', 'message': str(e)}))\n"
                        "if __name__ == '__main__':\n"
                        "    main()"
                    )
                }
            },
            "required": ["tool_name", "description", "tool_parameters", "code_content"]
        }

    async def execute(self, **kwargs) -> dict:
        tool_name = kwargs.get("tool_name")
        description = kwargs.get("description", "A generated task tool")
        tool_parameters = kwargs.get("tool_parameters", {"type": "object", "properties": {}})
        code_content = kwargs.get("code_content")

        if not tool_name or not code_content:
            return {"status": "error", "message": "Missing tool_name or code_content."}

        # 1. Validate Code (Security check: Whitelist imports, Banned functions)
        is_valid, errors = validate_tool_code(code_content)
        if not is_valid:
            error_msg = "; ".join(errors)
            return {"status": "error", "message": f"Validation Failed: {error_msg}"}

        # 2. Write File
        safe_name = tool_name.replace(" ", "_").lower()
        if not safe_name.startswith("dynamic_tool_"):
            filename = f"dynamic_tool_{safe_name}.py"
        else:
            filename = f"{safe_name}.py"

        category = kwargs.get("category", "general")
        safe_category = "".join(c for c in category if c.isalnum() or c in ("-", "_")).lower()
        if not safe_category:
            safe_category = "general"

        # 定位到 storage/dynamic_tools/{category}
        if self.registry and hasattr(self.registry, 'dynamic_path'):
            base_dir = self.registry.dynamic_path / safe_category
        else:
            # Fallback (如果在未完整依賴注入的情況下執行)
            base_dir = Path(__file__).resolve().parent.parent.parent.parent / "storage" / "dynamic_tools" / safe_category
            
        file_path = base_dir / filename
        
        import json
        schema_path = file_path.with_suffix('.json')
        schema_data = {
            "name": safe_name.replace("dynamic_tool_", "") if safe_name.startswith("dynamic_tool_") else safe_name,
            "category": safe_category,
            "description": description,
            "parameters": tool_parameters
        }
        
        async with self._lock:
            try:
                base_dir.mkdir(exist_ok=True, parents=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code_content)
                with open(schema_path, "w", encoding="utf-8") as f:
                    json.dump(schema_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                return {"status": "error", "message": f"File write failed: {e}"}

        # 3. Trigger Reload
        if not self.registry:
            return {
                "status": "warning", 
                "message": f"Skill '{tool_name}' created but registry was not injected."
            }

        try:
            refresh_result = await self.registry.refresh() 
            return {
                "status": "success",
                "message": f"Skill '{tool_name}' created and loaded. Total tools: {refresh_result.get('tool_count')}"
            }
        except Exception as e:
             return {"status": "warning", "message": f"Skill '{tool_name}' created but reload failed: {e}"}
