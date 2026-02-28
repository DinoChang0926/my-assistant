from copilot.tools import define_tool
from pydantic import BaseModel, Field
from typing import List


class ActivateToolsParams(BaseModel):
    categories: List[str] = Field(
        description="欲激活的工具類別清單 (例如: ['calendar', 'general', 'finance'])。"
    )


@define_tool(
    description=(
        "請求激活額外的工具類別 (Category)。\n"
        "當你發現當前已載入的工具無法滿足需求，但工具索引 (Tool Catalog) 中存在對應功能的類別時，請呼叫此工具。\n"
        "系統將會動態升級當前交談階段，載入該類別的完整工具定義 (Schema)。"
    )
)
async def activate_tools(params: ActivateToolsParams) -> dict:
    return {
        "status": "upgrade_signal",
        "message": (
            f"正在為您激活類別: {', '.join(params.categories)}。請稍候...\n"
            "[SYSTEM]: 升級請求已發送。系統將自動重啟會話並載入新工具定義。"
            "在此之前，請「停止」呼叫此工具及其它任何工具，直接等待系統重製訊息。"
        ),
        "requested_categories": params.categories,
    }


# --- Module exports for registry discovery (Phase 3a convention) ---
EXPORTED_TOOLS = [activate_tools]
TOOL_CATEGORY = "system"
