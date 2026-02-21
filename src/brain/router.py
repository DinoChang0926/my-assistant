import re
from src.core.events import AgentEvent
from src.core.interfaces import AbstractRouter, RouteConfig
from src.config import settings
from src.core.roles import RoleRegistry

class IntentClassifier(AbstractRouter):
    """
    Revised Router for Agent-Agent Delegation architecture.
    Routes almost all incoming traffic to the SUPERVISOR (Master Agent).
    The Master Agent is responsible for understanding the context and delegating
    work to EVOLUTION_MECHANIC or other workers via tools.
    """
    
    async def route(self, event: AgentEvent) -> RouteConfig:
        content = event.content.lower()
        
        # 僅保留極少數強制的架構輸出/純 Coding 模式，或直接完全交給 SUPERVISOR
        # 1. Architecture / Design (The "Strict Architect" worker)
        if any(kw in content for kw in ["架構圖", "mermaid", "目錄結構"]):
            role = RoleRegistry.ARCHITECT_STRICT
            return RouteConfig(
                model_name=settings.COPILOT_MODEL,
                system_prompt=role.system_prompt,
                intent="architecture",
                role=role
            )

        # 2. Master Agent (Supervisor)
        # All feature requests, tool creation, general chats go here.
        # The Supervisor will use 'delegate_to_mechanic' tool if it needs a new skill.
        role = RoleRegistry.SUPERVISOR
        return RouteConfig(
            model_name=settings.COPILOT_MODEL,
            system_prompt=role.system_prompt,
            intent="general",
            role=role
        )
