import re
from ..core.events import AgentEvent
from ..core.interfaces import AbstractRouter, RouteConfig
from .prompts import GENERAL_SYSTEM_PROMPT, CODING_ASSISTANT_PROMPT, CHAT_PROMPT, SELF_EVOLUTION_SYSTEM_PROMPT
from ..config import settings

class IntentClassifier(AbstractRouter):
    """Simple keyword-based semantic router."""
    
    async def route(self, event: AgentEvent) -> RouteConfig:
        content = event.content.lower()
        
        # Level 1: Command check (optional extension)
        if content.startswith("/reset"):
            return RouteConfig(
                model_name=settings.COPILOT_MODEL,
                system_prompt=GENERAL_SYSTEM_PROMPT + SELF_EVOLUTION_SYSTEM_PROMPT,
                intent="command_reset"
            )

        # Level 2: Intent Classification
        # Use Evolution Model for coding or tool-related tasks
        if any(kw in content for kw in ["程式", "寫一個", "debug", "python", "code", "函式", "實作", "工具", "tool", "create_tool"]):
            return RouteConfig(
                model_name=settings.COPILOT_EVOLUTION_MODEL,
                system_prompt=CODING_ASSISTANT_PROMPT + SELF_EVOLUTION_SYSTEM_PROMPT,
                intent="coding_evolution"
            )
        
        # Default Chat
        return RouteConfig(
            model_name=settings.COPILOT_MODEL,
            system_prompt=CHAT_PROMPT + SELF_EVOLUTION_SYSTEM_PROMPT,
            intent="general_chat"
        )
