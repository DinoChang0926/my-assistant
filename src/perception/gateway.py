from typing import Any, Callable, Awaitable, Optional
from src.core.events import AgentEvent, AgentResponse
from src.core.interfaces import AbstractRouter
# Orchestrator should be imported here once implemented

class UnifiedGateway:
    """The entry point that bridges Perception and Brain layers."""
    
    def __init__(self, router: AbstractRouter, orchestrator: Any):
        self.router = router
        self.orchestrator = orchestrator

    async def process(self, event: AgentEvent, status_callback: Optional[Callable[[str], Awaitable[None]]] = None) -> AgentResponse:
        """
        Normalize and route the event to the Brain layer.
        """
        print(f"Processing event {event.event_id} from {event.source}")
        
        # 1. Brain: Route the event to determine intent and model
        route_config = await self.router.route(event)
        
        # 2. Brain: Orchestrate the execution
        response = await self.orchestrator.execute(event, route_config, status_callback=status_callback)
        
        return response
