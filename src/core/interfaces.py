from abc import ABC, abstractmethod
from typing import List, Optional, Any
from dataclasses import dataclass
from src.core.events import AgentEvent, AgentResponse

from src.core.roles import AgentRole

@dataclass
class RouteConfig:
    """Configuration for LLM routing."""
    model_name: str
    system_prompt: str  # Kept for backward compatibility or direct overrides
    intent: str
    role: Optional[AgentRole] = None

class AbstractRouter(ABC):
    @abstractmethod
    async def route(self, event: AgentEvent) -> RouteConfig:
        pass

class AbstractTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict:
        pass

    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        pass

class AbstractSessionManager(ABC):
    @abstractmethod
    async def get_or_create(self, session_id: str, route_config: RouteConfig) -> Any:
        pass

    @abstractmethod
    async def cleanup(self, session_id: str):
        pass
