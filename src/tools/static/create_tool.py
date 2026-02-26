import sys
import subprocess
import asyncio
import json
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
                },
                "test_code": {
                    "type": "string",
                    "description": (
                        "針對此工具的 pytest 單元測試程式碼。\n"
                        "⚠️ 測試必須通過才能完成工具建立。\n"
                        "⚠️ 測試透過 subprocess 呼叫工具腳本，驗證 stdin→stdout 的 JSON 契約。\n"
                        "💡 [測試骨架]:\n"
                        "import subprocess, sys, json, pytest\n"
                        "SCRIPT = __file__.replace('test_dynamic_tool_', 'dynamic_tool_')\n"
                        "def run_tool(input_data: dict) -> dict:\n"
                        "    proc = subprocess.run([sys.executable, SCRIPT],\n"
                        "        input=json.dumps(input_data), capture_output=True, text=True, timeout=10)\n"
                        "    assert proc.returncode == 0, f'Script failed: {proc.stderr}'\n"
                        "    return json.loads(proc.stdout.strip().split(chr(10))[-1])\n"
                        "def test_basic():\n"
                        "    result = run_tool({'param': 'value'})\n"
                        "    assert result['status'] == 'success'\n"
                    )
                }
            },
            "required": ["tool_name", "description", "tool_parameters", "code_content", "test_code"]
        }

    async def execute(self, **kwargs) -> dict:
        tool_name = kwargs.get("tool_name")
        description = kwargs.get("description", "A generated task tool")
        tool_parameters = kwargs.get("tool_parameters", {"type": "object", "properties": {}})
        code_content = kwargs.get("code_content")
        test_code = kwargs.get("test_code")

        if not tool_name or not code_content:
            return {"status": "error", "message": "Missing tool_name or code_content."}

        if not test_code:
            return {"status": "error", "message": "Missing test_code. 建立工具時必須同時提供單元測試程式碼。"}

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
        
        schema_path = file_path.with_suffix('.json')
        schema_data = {
            "name": safe_name.replace("dynamic_tool_", "") if safe_name.startswith("dynamic_tool_") else safe_name,
            "category": safe_category,
            "description": description,
            "parameters": tool_parameters
        }
        
        # Build test file path
        test_filename = f"test_{filename}"  # e.g. test_dynamic_tool_xxx.py
        test_path = base_dir / test_filename

        async with self._lock:
            try:
                base_dir.mkdir(exist_ok=True, parents=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code_content)
                with open(schema_path, "w", encoding="utf-8") as f:
                    json.dump(schema_data, f, ensure_ascii=False, indent=2)
                with open(test_path, "w", encoding="utf-8") as f:
                    f.write(test_code)
            except Exception as e:
                return {"status": "error", "message": f"File write failed: {e}"}

        # 3. Run unit tests — must pass before completing
        try:
            test_result = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pytest", str(test_path), "-v", "--tb=short", "-q",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    test_result.communicate(), timeout=30.0
                )
            except asyncio.TimeoutError:
                test_result.kill()
                # Rollback: remove the created files
                self._cleanup_files(file_path, schema_path, test_path)
                return {"status": "error", "message": "單元測試執行逾時 (30s)，工具建立已取消。"}

            if test_result.returncode != 0:
                test_output = stdout.decode('utf-8', errors='replace') + "\n" + stderr.decode('utf-8', errors='replace')
                # Rollback: remove the created files
                self._cleanup_files(file_path, schema_path, test_path)
                return {
                    "status": "error",
                    "message": f"單元測試未通過，工具建立已取消。請修正後重試。",
                    "test_output": test_output.strip()[-2000:]  # 最多回傳 2000 字元
                }
        except Exception as e:
            self._cleanup_files(file_path, schema_path, test_path)
            return {"status": "error", "message": f"單元測試執行失敗: {e}"}

        # 4. Trigger Reload
        if not self.registry:
            return {
                "status": "warning", 
                "message": f"Skill '{tool_name}' created but registry was not injected."
            }

        try:
            refresh_result = await self.registry.refresh() 
            return {
                "status": "success",
                "message": f"Skill '{tool_name}' created (with passing tests) and loaded. Total tools: {refresh_result.get('tool_count')}"
            }
        except Exception as e:
             return {"status": "warning", "message": f"Skill '{tool_name}' created (tests passed) but reload failed: {e}"}

    @staticmethod
    def _cleanup_files(*paths):
        """Remove files created during a failed tool creation attempt."""
        for p in paths:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
