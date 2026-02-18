from src.tools.base import BaseTool
from src.perception import rest_api

class ReloadToolsTool(BaseTool):
    """
    A static tool that allows the Agent to trigger a refresh of the tool registry.
    This is essential for the self-evolution loop: Create -> Reload -> Execute.
    """
    
    @property
    def name(self) -> str:
        return "reload_tools"
    
    @property
    def description(self) -> str:
        return "重新載入所有動態工具。當新工具被建立後，呼叫此工具以刷新工具清單，使新工具立即可用。"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self, **kwargs) -> dict:
        print(f"Agent triggered tool reload...")
        if rest_api.tool_registry:
            return await rest_api.tool_registry.refresh()
        return {"status": "error", "message": "ToolRegistry not found in rest_api"}
