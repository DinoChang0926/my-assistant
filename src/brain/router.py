from src.core.events import AgentEvent
from src.core.interfaces import AbstractRouter, RouteConfig
from src.config import settings
from src.core.roles import RoleRegistry

# Architecture-specific keywords that bypass the Supervisor
_ARCHITECTURE_KEYWORDS = frozenset({"架構圖", "mermaid", "目錄結構"})


class IntentClassifier(AbstractRouter):
    """
    Lightweight intent router (Phase 4 simplified).

    Design decisions:
    - SUPERVISOR handles ~99% of traffic (general chat, coding, tool use).
    - ARCHITECT_STRICT activates only for explicit architecture / diagram keywords.
    - EVOLUTION_MECHANIC is invoked solely by ``delegate_to_mechanic`` tool,
      never by this router (background execution requires independent sessions).
    - CODER_GENERAL was removed: the Supervisor delegates coding tasks via tools.
    - SDK ``custom_agents`` evaluated and deferred: background delegation via
      ``asyncio.create_task`` is incompatible with shared-session agent model.
    """

    async def route(self, event: AgentEvent) -> RouteConfig:
        content = event.content.lower()

        if any(kw in content for kw in _ARCHITECTURE_KEYWORDS):
            role = RoleRegistry.ARCHITECT_STRICT
            return RouteConfig(
                model_name=settings.COPILOT_MODEL,
                system_prompt=role.system_prompt,
                intent="architecture",
                role=role,
            )

        role = RoleRegistry.SUPERVISOR
        return RouteConfig(
            model_name=settings.COPILOT_MODEL,
            system_prompt=role.system_prompt,
            intent="general",
            role=role,
        )
