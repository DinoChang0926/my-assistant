from pathlib import Path
from src.tools.base import BaseTool

class InspectToolTool(BaseTool):
    """
    Allows the Agent to read the source code of an existing tool.
    """

    @property
    def name(self) -> str:
        return "inspect_tool"

    @property
    def description(self) -> str:
        return "讀取現有工具的 Python 原始碼。當需要修改、優化或學習現有工具實作時使用。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "工具名稱"
                }
            },
            "required": ["tool_name"]
        }

    async def execute(self, **kwargs) -> dict:
        tool_name = kwargs.get("tool_name")
        if not tool_name:
            return {"status": "error", "message": "Missing tool_name."}

        base_dir = Path(__file__).parent.parent
        search_paths = [base_dir / "static", base_dir / "dynamic"]

        found_path = None
        for path in search_paths:
            p1 = path / f"{tool_name}.py"
            if p1.exists():
                found_path = p1
                break
            p2 = path / f"dynamic_tool_{tool_name}.py"
            if p2.exists():
                found_path = p2
                break
            p3 = path / f"static_tool_{tool_name}.py"
            if p3.exists():
                found_path = p3
                break

        if not found_path:
            return {"status": "error", "message": f"Tool '{tool_name}' not found."}

        try:
            with open(found_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {
                "status": "success",
                "tool_name": tool_name,
                "file_path": str(found_path),
                "code": content
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to read tool file: {e}"}
