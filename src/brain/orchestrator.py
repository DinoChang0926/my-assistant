import asyncio
from typing import Any, List
from ..core.events import AgentEvent, AgentResponse
from ..core.interfaces import RouteConfig
from ..memory.manager import SessionManager
from ..tools.registry import ToolRegistry
from .prompts import SKILL_ACQUISITION_PROMPT
from copilot import MessageOptions

class TaskOrchestrator:
    """Coordinates the execution flow between Memory, SDK, and Tools."""
    
    def __init__(self, session_manager: SessionManager, tool_registry: ToolRegistry):
        self.session_manager = session_manager
        self.tool_registry = tool_registry

    async def execute(self, event: AgentEvent, route_config: RouteConfig) -> AgentResponse:
        # 1. Get or create session
        wrapper = await self.session_manager.get_or_create(event.session_id, route_config)
        session = wrapper.sdk_session
        
        # 2. Inject system prompt if newly created or respawned (simplified)
        # GitHub Copilot SDK uses 'system_prompt' in create_session or through initial message
        
        # 3. Prepare tools
        tool_schemas = self.tool_registry.get_all_schemas()
        

        # 4. Define local event handler for tool execution
        tool_calls = []
        
        def handle_tool(event_obj: Any):
            e_type = event_obj.type.value if hasattr(event_obj.type, 'value') else str(event_obj.type)
            print(f"Captured event: {e_type}")
            if e_type in ["tool.execution", "tool.execution_start"]:
                asyncio.create_task(self._process_tool_execution(session, event_obj, tool_calls))

        # Register handler
        unsubscribe = session.on(handle_tool)
        
        # 5. Send message and wait for idle
        done_event = asyncio.Event()
        final_content = ""

        def handle_response(event_obj: Any):
            nonlocal final_content
            e_type = event_obj.type.value if hasattr(event_obj.type, 'value') else str(event_obj.type)
            print(f"Captured response event: {e_type}")
            if e_type == "assistant.message":
                final_content = event_obj.data.content
                print(f"Assistant message received: {final_content[:50]}...")
            elif e_type == "session.idle":
                print("Session idle, finishing...")
                done_event.set()
            elif e_type == "session.error":
                print(f"SDK Error: {event_obj.data.message}")
                done_event.set()

        session.on(handle_response)
        
        # Send
        await session.send(MessageOptions(prompt=event.content))
        
        # Wait
        await done_event.wait()
        
        # Unsubscribe handlers
        unsubscribe()
        
        # Update turn count
        wrapper.turn_count += 1
        
        return AgentResponse(
            content=final_content,
            tool_calls=tool_calls
        )

    async def _process_tool_execution(self, session: Any, event_obj: Any, tool_calls: List[dict]):
        data = event_obj.data
        t_name = getattr(data, 'tool_name', None) or getattr(data, 'name', None)
        t_call_id = getattr(data, 'tool_call_id', None) or getattr(data, 'call_id', None)
        t_args = getattr(data, 'arguments', None)
        
        tool_call = {
            "name": t_name,
            "arguments": t_args,
            "id": t_call_id
        }
        tool_calls.append(tool_call)
        
        # Execute tool
        tool = self.tool_registry.get_tool(t_name)
        error_context = None

        if tool:
            print(f"Executing tool: {tool.name}")
            try:
                result = await tool.execute(**t_args) if t_args else await tool.execute()
            except Exception as e:
                import traceback
                error_msg = f"Tool '{t_name}' execution failed: {str(e)}\n{traceback.format_exc()}"
                print(error_msg)
                error_context = error_msg
                result = {"status": "error", "message": error_msg}
        else:
            error_msg = f"Tool '{t_name}' not found in registry."
            print(error_msg)
            error_context = error_msg
            result = {"status": "error", "message": error_msg}

        # Submit tool result back to session
        # If there was an error, we append the SKILL_ACQUISITION_PROMPT to the result
        output_content = str(result)
        if error_context:
            output_content += "\n\n" + SKILL_ACQUISITION_PROMPT.format(error_context=error_context)

        try:
            if hasattr(session, 'submit_tool_outputs'):
                await session.submit_tool_outputs([{
                    "call_id": t_call_id,
                    "output": output_content
                }])
            else:
                # Fallback to internal protocol call
                await session._client.request("session.submitToolOutputs", {
                    "sessionId": session.session_id,
                    "outputs": [{
                        "callId": t_call_id,
                        "output": output_content
                    }]
                })
        except Exception as e:
            print(f"Failed to submit tool outputs: {e}")
