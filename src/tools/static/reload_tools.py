import asyncio
from src.tools.base import BaseTool

class ReloadToolsTool(BaseTool):
    """
    A tool that triggers a hot-reload of all tools in the registry.
    """

    def __init__(self, registry=None):
        """
        Args:
            registry: ToolRegistry instance (Dependency Injection)
        """
        self.registry = registry

    @property
    def name(self) -> str:
        return "reload_tools"

    @property
    def category(self) -> str:
        return "system"

    @property
    def description(self) -> str:
        return "熱重載所有技能。當手動修改技能程式碼或新增檔案後，執行此技能以立即生效。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {}
        }

    async def execute(self, **kwargs) -> dict:
        print(f"Agent triggered skill reload...")
        if not self.registry:
            return {"status": "error", "message": "ToolRegistry not injected into ReloadToolsTool"}
            
        try:
            refresh_result = await self.registry.refresh()
            return {
                "status": "success",
                "message": f"Skills hot-reloaded successfully. Total skills: {refresh_result.get('tool_count', 0)}"
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to refresh skills: {e}"}
