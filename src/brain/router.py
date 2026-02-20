import re
from src.core.events import AgentEvent
from src.core.interfaces import AbstractRouter, RouteConfig
from src.brain.prompts import GENERAL_SYSTEM_PROMPT, CODING_ASSISTANT_PROMPT, CHAT_PROMPT, SELF_EVOLUTION_SYSTEM_PROMPT
from src.config import settings

from src.core.roles import RoleRegistry
from src.brain.prompts import SELF_EVOLUTION_SYSTEM_PROMPT

class IntentClassifier(AbstractRouter):
    """Refined keyword-based semantic router for Supervisor-Worker architecture."""
    
    async def route(self, event: AgentEvent) -> RouteConfig:
        content = event.content.lower()
        
        # 1. Environment / Self-Evolution (The "Evolution Mechanic" worker)
        # Handle "stale" issues or environment-specific needs
        if any(kw in content for kw in ["create_tool", "建立工具", "建立技能", "修復工具", "環境", "shell", "powershell"]):
            role = RoleRegistry.EVOLUTION_MECHANIC
            return RouteConfig(
                model_name=settings.COPILOT_EVOLUTION_MODEL,
                system_prompt=(role.system_prompt or "") + SELF_EVOLUTION_SYSTEM_PROMPT,
                intent="evolution",
                role=role
            )

        # 2. Architecture / Design (The "Strict Architect" worker)
        if any(kw in content for kw in ["架構", "設計", "架構圖", "mermaid", "目錄結構", "architecture", "design", "structure"]):
            role = RoleRegistry.ARCHITECT_STRICT
            return RouteConfig(
                model_name=settings.COPILOT_MODEL,
                system_prompt=role.system_prompt,
                intent="architecture",
                role=role
            )

        # 3. Coding (The "General Coder" worker)
        if any(kw in content for kw in ["程式", "寫一個", "debug", "python", "code", "函式", "實作", "寫code"]):
            role = RoleRegistry.CODER_GENERAL
            return RouteConfig(
                model_name=settings.COPILOT_EVOLUTION_MODEL,
                system_prompt=role.system_prompt, # Usually None for native behavior
                intent="coding",
                role=role
            )
        
        # 4. Default: Supervisor (General Chat, native behavior)
        role = RoleRegistry.SUPERVISOR
        return RouteConfig(
            model_name=settings.COPILOT_MODEL,
            system_prompt=role.system_prompt,
            intent="general",
            role=role
        )
