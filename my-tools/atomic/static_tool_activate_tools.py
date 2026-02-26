from typing import Any, Dict, List
from src.tools.base import BaseTool

class ActivateToolsTool(BaseTool):
    """
    Meta-tool that allows the Agent to request activation of additional tool categories.
    When executed, it returns a signal that the Orchestrator intercepts to rebuild the session with more tools.
    """

    @property
    def name(self) -> str:
        return "activate_tools"

    @property
    def category(self) -> str:
        return "system"

    @property
    def description(self) -> str:
        return (
            "請求激活額外的工具類別 (Category)。\n"
            "當你發現當前已載入的工具無法滿足需求，但工具索引 (Tool Catalog) 中存在對應功能的類別時，請呼叫此工具。\n"
            "系統將會動態升級當前交談階段，載入該類別的完整工具定義 (Schema)。"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "欲激活的工具類別清單 (例如: ['calendar', 'general', 'finance'])。"
                }
            },
            "required": ["categories"]
        }

    async def execute(self, categories: List[str], **kwargs) -> Dict[str, Any]:
        # The Orchestrator intercepts this specific return structure
        return {
            "status": "upgrade_signal",
            "message": (
                f"正在為您激活類別: {', '.join(categories)}。請稍候...\n"
                "[SYSTEM]: 升級請求已發送。系統將自動重啟會話並載入新工具定義。在此之前，請「停止」呼叫此工具及其它任何工具，直接等待系統重製訊息。"
            ),
            "requested_categories": categories
        }
