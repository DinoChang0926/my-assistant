"""Core data structures for the AI Agent system."""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class InputSource(str, Enum):
    """Source of the input event."""
    API = "api"
    TELEGRAM = "telegram"


class AgentEvent(BaseModel):
    """Standardized input event from any source."""
    event_id: str
    source: InputSource
    session_id: str  # User ID / Chat ID for memory correlation
    content: str     # User's original input
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Source-specific info


class AgentResponse(BaseModel):
    """Standardized output response."""
    content: str                        # LLM's final response
    tool_calls: List[Dict] = Field(default_factory=list)  # Tools executed during processing
    metadata: Dict[str, Any] = Field(default_factory=dict)
