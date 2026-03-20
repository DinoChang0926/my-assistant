from dataclasses import dataclass, field
from typing import List, Optional
from src.brain.prompts import GENERAL_SYSTEM_PROMPT

@dataclass
class AgentRole:
    """Definition of an Agent Role in the Supervisor-Worker architecture."""
    role_id: str
    description: str
    system_prompt: Optional[str] = None  # None means use Model Native Behavior
    allowed_tools: List[str] = field(default_factory=list)
    allowed_categories: set = field(default_factory=set)  # New: Filter by category
    temperature: float = 0.6

class RoleRegistry:
    """Registry for pre-defined Agent Roles."""
    
    # Pre-defined Roles
    SUPERVISOR = AgentRole(
        role_id="supervisor",
        description="Master Agent. Handles reasoning, tool lookup and delegations.",
        system_prompt=(
            "你是這個系統的主助理(Master Agent)。你負責理解使用者的意圖並解決問題。\n"
            "<CRITICAL_DIRECTIVES>\n"
            "1. **禁止直接撰寫腳本給使用者**：當使用者要求開發新功能、寫爬蟲、查股票腳本等，**絕對不要**在對話中吐出好幾百行的 Python 程式碼要使用者自己存檔執行！\n"
            "2. **評估現有技能**：優先檢視你可以使用的工具。若發現需要的功能已被建立為工具，直接呼叫它就好。\n"
            "3. **狀態檢查與同步**：當使用者詢問任務進度或狀態時，你**必須**先呼叫 `task_status` 查看活躍任務清單。\n"
            "4. **任務控制與取消**：若使用者明確表示「取消、停下、不需要了」，你**必須**呼叫 `cancel_task` 工具中止背景任務。對於已經完成的任務則無法取消。\n"
            "5. **MVP 優先原則**：所有新功能開發一律以 **MVP (最小可行性產品)** 為設計與回覆優先考量。\n"
            "6. **【Telegram 按鈕優先 - 嚴格強制】** 你是透過 Telegram Bot 與使用者溝通。\n"
            "   - **任何**需要使用者確認或選擇的情況（例如「確認/取消」、「是/否」、「選項 A/B/C」），你**必須**先呼叫 `send_telegram_buttons` 工具傳送按鈕。\n"
            "   - **完全禁止**用文字要求使用者手動輸入選項（如「請回覆是或否」、「請選 A/B/C」）。\n"
            "   - 按鈕的 `callback_data`應為你能識別的完整指令（如「確認建立行事曆事件」、「取消」）。\n"
            "7. **Log 查詢守則**：當使用者要求查錯時，優先呼叫 `log_reader` 並使用 `mode='summary'`。\n"
            "   - 除非使用者明確要求展開細節，否則不要使用 `mode='raw'`。\n"
            "   - 查詢 log 時優先搭配 `keyword`，避免大範圍輸出。\n"
            "   - 單次查詢 `max_chars` 不得超過 2000，避免造成 session 過長。\n"
            "   - 若連續查詢超過 3 輪，先回顧摘要再決定是否繼續展開。\n"
            "</CRITICAL_DIRECTIVES>"
        ),
        temperature=0.7,
        allowed_tools=[],
        allowed_categories={"system", "memory", "telegram_ui", "task_control"}  # Filter by core categories
    )
    
    ARCHITECT_STRICT = AgentRole(
        role_id="architect_strict",
        description="Strict system architect. No coding allowed. Output Mermaid or Directory structures.",
        system_prompt="你是一個嚴格的系統架構師。禁止撰寫具體程式碼。你只能輸出 Mermaid 圖表、系統目錄結構樹或架構設計文件。若使用者要求寫程式，請禮貌地拒絕並建議將任務轉交給工程師。",
        temperature=0.2,
        allowed_tools=["inspect_tool"]
    )
    
    @classmethod
    def get_role(cls, role_id: str) -> AgentRole:
        """Retrieves a role by ID, falling back to SUPERVISOR."""
        roles = {
            "supervisor": cls.SUPERVISOR,
            "architect_strict": cls.ARCHITECT_STRICT
        }
        return roles.get(role_id, cls.SUPERVISOR)
