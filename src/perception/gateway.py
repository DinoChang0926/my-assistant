import asyncio
import logging
from typing import Any, Callable, Awaitable, Dict, Optional
from src.core.events import AgentEvent, AgentResponse
from src.core.interfaces import AbstractRouter

logger = logging.getLogger("src.perception.gateway")

class UnifiedGateway:
    """The entry point that bridges Perception and Brain layers."""
    
    def __init__(self, router: AbstractRouter, orchestrator: Any):
        self.router = router
        self.orchestrator = orchestrator
        self._session_locks: Dict[str, asyncio.Lock] = {}

    async def process(self, event: AgentEvent, status_callback: Optional[Callable[[str], Awaitable[None]]] = None) -> AgentResponse:
        """
        Normalize and route the event to the Brain layer.
        Serializes requests per session to prevent concurrent SDK calls.
        """
        logger.info(f"Processing event {event.event_id} from {event.source}")

        lock = self._session_locks.setdefault(event.session_id, asyncio.Lock())
        if lock.locked():
            logger.warning(f"Session {event.session_id} is busy. Returning early.")
            return AgentResponse(
                content="⏳ 上一則訊息仍在處理中，請稍候再試。",
                tool_calls=[],
            )

        async with lock:
            # 1. Brain: Route the event to determine intent and model
            route_config = await self.router.route(event)
            
            # 2. Brain: Orchestrate the execution
            response = await self.orchestrator.execute(event, route_config, status_callback=status_callback)
            
            return response
