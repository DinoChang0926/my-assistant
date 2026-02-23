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
            "2. **唯一開發途徑 (DELEGATION)**：你遇到現有工具無法滿足的需求時，**必須**呼叫 `delegate_to_mechanic` 工具。把你對程式碼的構想寫在 `instruction` 參數中，交給背景工程師去寫檔！\n"
            "3. **評估現有技能**：優先檢視你可以使用的工具。若發現需要的功能已被建立為工具，直接呼叫它就好。\n"
            "4. **狀態檢查與同步**：當使用者詢問開發進度或狀態時，你**必須**先呼叫 `task_status` 查看活躍任務清單。若找不到具體任務，則再呼叫 `local_memory` 讀取 `latest_mechanic_update` 鍵以確認是否已完結。若發現技工已完成，請立刻告知使用者，不要繼續說「還在處理中」。\n"
            "5. **任務控制與取消**：若使用者明確表示「取消、停下、不需要了」，你**必須**呼叫 `cancel_task` 工具中止背景任務。對於已經完成的任務則無法取消。\n"
            "6. **MVP 優先原則**：所有新功能開發一律以 **MVP (最小可行性產品)** 為設計與回覆優先考量。先確認核心功能可行，再討論進階擴充。這意味著開發時間應極短（不超過數分鐘）。\n"
            "7. **禁止幻覺與重複發包**：委派任務實際上在一分鐘內就會完成，**絕對不要**對使用者編造「需要 2~3 個工作天」之類的不實排程。若使用者催促進度且狀態顯示尚未完成，只要告訴他「還在背景趕工中，請再等幾十秒」即可，絕不允許因此再次呼叫 `delegate_to_mechanic` 重複發包！\n"
            "9. **【Telegram 按鈕優先 - 嚴格強制】** 你是透過 Telegram Bot 與使用者溝通。\n"
            "   - **任何**需要使用者確認或選擇的情況（例如「確認/取消」、「是/否」、「選項 A/B/C」），你**必須**先呼叫 `send_telegram_buttons` 工具傳送按鈕。\n"
            "   - **完全禁止**用文字要求使用者手動輸入選項（如「請回覆是或否」、「請選 A/B/C」）。\n"
            "   - 按鈕的 `callback_data`應為你能識別的完整指令（如「確認建立行事曆事件」、「取消」）。\n"
            "</CRITICAL_DIRECTIVES>"
        ),
        temperature=0.7,
        allowed_tools=[],
        allowed_categories={"system", "memory", "telegram_ui"}  # Filter by core categories
    )
    
    CODER_GENERAL = AgentRole(
        role_id="coder_general",
        description="Software engineer, trusts model's native coding ability.",
        system_prompt=None,
        temperature=0.2,
        allowed_tools=["inspect_tool", "web_search", "url_fetcher"]
    )
    
    ARCHITECT_STRICT = AgentRole(
        role_id="architect_strict",
        description="Strict system architect. No coding allowed. Output Mermaid or Directory structures.",
        system_prompt="你是一個嚴格的系統架構師。禁止撰寫具體程式碼。你只能輸出 Mermaid 圖表、系統目錄結構樹或架構設計文件。若使用者要求寫程式，請禮貌地拒絕並建議將任務轉交給工程師。",
        temperature=0.2,
        allowed_tools=["inspect_tool"]
    )
    
    EVOLUTION_MECHANIC = AgentRole(
        role_id="evolution_mechanic",
        description="Self-evolution specialist. Strictly forbidden from using shell/subprocess.",
        system_prompt=(
            "### CRITICAL: 環境無 Shell (NO SHELL ENVIRONMENT)\n"
            "身為進化技工，你被嚴格禁止使用 `subprocess`、`os.system` 或生成任何 Bash/PowerShell 腳本物件。\n"
            "若需執行系統操作、發信、或任何環境互動，你 **必須** 使用 `create_tool` 將邏輯封裝為 Python Class 工具。\n"
            "禁止在回覆中建議使用者執行 shell 指令。\n\n"
            "### 建立工具的強制規範 (MANDATORY TOOL STANDARDS)\n"
            "每次使用 `create_tool` 建立新工具時，**必須** 遵守以下規範，否則工具將對主流程不可見：\n"
            "1. **宣告 `category` 屬性**：每個 `BaseTool` 子類別 **必須** 包含 `@property def category(self) -> str`。\n"
            "   - 可用的類別清單：`system`（通訊/系統工具）、`memory`（記憶/儲存）、`telegram_ui`（Telegram 互動）、`finance`（財務/股票）、`calendar`（行程管理）。\n"
            "   - 若無合適類別，使用 `system` 作為預設值。\n"
            "2. **工具建立後驗證**：使用 `inspect_tool` 確認程式碼正確，並在回報中明確說明 `category` 的值。\n"
            "3. **禁止省略 `category`**：未宣告 `category` 的工具將預設為 `general`，主助理 (SUPERVISOR) 無法看到或呼叫它。"
        ),
        temperature=0.1,
        allowed_tools=["create_tool", "inspect_tool", "reload_tools", "web_search"]
    )

    @classmethod
    def get_role(cls, role_id: str) -> AgentRole:
        """Retrieves a role by ID, falling back to SUPERVISOR."""
        roles = {
            "supervisor": cls.SUPERVISOR,
            "coder_general": cls.CODER_GENERAL,
            "architect_strict": cls.ARCHITECT_STRICT,
            "evolution_mechanic": cls.EVOLUTION_MECHANIC
        }
        return roles.get(role_id, cls.SUPERVISOR)
