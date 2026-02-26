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
    def category(self) -> str:
        return "diagnostic"

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
        project_root = base_dir.parent.parent
        static_path = base_dir / "static"
        atomic_path = project_root / "my-tools" / "atomic"
        dynamic_path = project_root / "storage" / "dynamic_tools"

        found_path = None
        
        # 1. 搜尋 meta-skills (src/tools/static/)
        p1 = static_path / f"{tool_name}.py"
        p2 = static_path / f"static_tool_{tool_name}.py"
        if p1.exists():
            found_path = p1
        elif p2.exists():
            found_path = p2

        # 2. 搜尋 atomic tools (my-tools/atomic/)
        if not found_path and atomic_path.exists():
            for p in atomic_path.rglob("*.py"):
                if p.name == f"{tool_name}.py" or p.name == f"static_tool_{tool_name}.py":
                    found_path = p
                    break
            
        # 3. 搜尋 dynamic 技能 (因為可能有分類資料夾，所以用 rglob)
        if not found_path and dynamic_path.exists():
            for p in dynamic_path.rglob("*.py"):
                if p.name == f"{tool_name}.py" or p.name == f"dynamic_tool_{tool_name}.py":
                    found_path = p
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
