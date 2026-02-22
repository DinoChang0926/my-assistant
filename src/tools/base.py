from abc import ABC, abstractmethod
from typing import Any, Dict
from src.core.interfaces import AbstractTool

class BaseTool(AbstractTool, ABC):
    """Base class for all tools."""

    @property
    def category(self) -> str:
        """Category to group tools (e.g., 'system', 'finance', 'task_control')."""
        return "general"
    
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

    def to_schema(self) -> dict:
        """Convert tool definition to GitHub Copilot SDK compatible schema."""
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "parameters": self.parameters
        }
