from typing import Dict, List
from .base import BaseTool

class ToolRegistry:
    """Registry to manage and retrieve tools."""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        print(f"Tool registered: {tool.name}")

    def get_tool(self, name: str) -> BaseTool:
        return self._tools.get(name)

    def get_all_schemas(self) -> List[dict]:
        return [tool.to_schema() for tool in self._tools.values()]

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())
