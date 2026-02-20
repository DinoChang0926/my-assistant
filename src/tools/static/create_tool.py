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
                "code_content": {
                    "type": "string",
                    "description": "完整的 Python 程式碼 (應繼承 BaseTool)。禁止使用 subprocess 或未安裝的庫。"
                }
            },
            "required": ["tool_name", "code_content"]
        }

    async def execute(self, **kwargs) -> dict:
        tool_name = kwargs.get("tool_name")
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

        # 定位到 src/tools/dynamic
        base_dir = Path(__file__).resolve().parent.parent / "dynamic"
        file_path = base_dir / filename
        
        async with self._lock:
            try:
                base_dir.mkdir(exist_ok=True, parents=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code_content)
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
