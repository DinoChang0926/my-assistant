import re
from ..core.events import AgentEvent
from ..core.interfaces import AbstractRouter, RouteConfig
from .prompts import GENERAL_SYSTEM_PROMPT, CODING_ASSISTANT_PROMPT, CHAT_PROMPT
from ..config import settings

class IntentClassifier(AbstractRouter):
    """Simple keyword-based semantic router."""
    
    async def route(self, event: AgentEvent) -> RouteConfig:
        content = event.content.lower()
        
        # Level 1: Command check (optional extension)
        if content.startswith("/reset"):
            return RouteConfig(
                model_name=settings.COPILOT_MODEL,
                system_prompt=GENERAL_SYSTEM_PROMPT,
                intent="command_reset"
            )

        # Level 2: Intent Classification
        if any(kw in content for kw in ["程式", "寫一個", "debug", "python", "code", "函式", "實作"]):
            return RouteConfig(
                model_name=settings.COPILOT_MODEL,
                system_prompt=CODING_ASSISTANT_PROMPT,
                intent="coding"
            )
        
        # Default Chat
        return RouteConfig(
            model_name=settings.COPILOT_MODEL,
            system_prompt=CHAT_PROMPT,
            intent="general_chat"
        )
