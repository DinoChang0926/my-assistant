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
    temperature: float = 0.6

class RoleRegistry:
    """Registry for pre-defined Agent Roles."""
    
    SUPERVISOR = AgentRole(
        role_id="supervisor",
        description="Friendly general assistant, preserves model's native persona.",
        system_prompt=GENERAL_SYSTEM_PROMPT,
        temperature=0.7,
        allowed_tools=["web_search", "url_fetcher", "local_memory"]
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
            "禁止在回覆中建議使用者執行 shell 指令。"
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
