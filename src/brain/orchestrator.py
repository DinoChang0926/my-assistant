import asyncio
import re
from typing import Any, List, Callable, Awaitable, Optional
from src.core.events import AgentEvent, AgentResponse
from src.core.interfaces import RouteConfig
from src.memory.manager import SessionManager
from src.tools.registry import ToolRegistry
from src.brain.prompts import SKILL_ACQUISITION_PROMPT
from copilot import MessageOptions

class TaskOrchestrator:
    """Coordinates the execution flow between Memory, SDK, and Tools."""
    
    def __init__(self, session_manager: SessionManager, tool_registry: ToolRegistry):
        self.session_manager = session_manager
        self.tool_registry = tool_registry

    async def execute(self, event: AgentEvent, route_config: RouteConfig, status_callback: Optional[Callable[[str], Awaitable[None]]] = None) -> AgentResponse:
        # 0. Hot Reload Tools
        # Ensure we pick up any newly created tools (Self-Evolution)
        await self.tool_registry.refresh()

        # 1. Prepare tools for SDK
        # Convert BaseTools to SDK Tool objects with handlers
        sdk_tools = []
        base_tools = list(self.tool_registry._tools.values())
        
        # Filter tools if specific allowed_tools are defined for the role
        if route_config.role and route_config.role.allowed_tools:
            allowed_names = set(route_config.role.allowed_tools)
            base_tools = [t for t in base_tools if t.name in allowed_names]
            print(f"[Orchestrator] Filtering tools for role '{route_config.role.role_id}': {allowed_names}")
        
        # We need to import these locally to avoid circular imports or early import issues
        from copilot.types import Tool, ToolInvocation, ToolResult
        
        for tool in base_tools:
            # Handler Wrapper: Adapts Agent's BaseTool execution to SDK's expected format
            def make_handler(t_instance):
                async def handler(invocation: ToolInvocation) -> ToolResult:
                    print(f"SDK Tool Handler invoked for: {t_instance.name}")
                    try:
                        args = invocation.get("arguments", {})
                        if args is None: args = {}
                        
                        result_data = await t_instance.execute(**args)
                        
                        return {
                            "resultType": "success",
                            "textResultForLlm": str(result_data)
                        }
                    except Exception as e:
                        import traceback
                        error_msg = f"Tool '{t_instance.name}' execution failed: {str(e)}\n{traceback.format_exc()}"
                        print(error_msg)
                        return {
                            "resultType": "failure", 
                            "error": error_msg,
                            "textResultForLlm": f"Error: {error_msg}\n\n{SKILL_ACQUISITION_PROMPT.format(error_context=error_msg)}"
                        }
                return handler
            
            sdk_tools.append(Tool(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                handler=make_handler(tool)
            ))
        
        # 1.5 Inject Skill List into System Prompt
        # This ensures the Agent knows what it can do BEFORE it tries.
        skill_list_str = "\n".join([f"- {t.name}: {t.description}" for t in base_tools])
        if not skill_list_str:
            skill_list_str = "(No unlocked skills available, please use create_tool to create one)"

        # 追加嚴格指令，禁止輸出思考過程
        strict_instruction = "\n\n[CRITICAL]: 當你需要呼叫工具 (Tool) 時，請「直接」呼叫工具，絕對不要在訊息中輸出你的思考過程 (Chain of Thought)、自我解釋或英文的抓取動作描述 (如 'Fetching...', 'Let me check...' 等)。只需要把最終結論告訴使用者即可。"

        current_prompt = route_config.system_prompt
        if current_prompt:
            if "{skill_list}" in current_prompt:
                 route_config.system_prompt = current_prompt.replace("{skill_list}", skill_list_str) + strict_instruction
            elif "### Current Skills:" not in current_prompt:
                # Fallback: specific injection or just append if not found
                route_config.system_prompt = current_prompt + f"\n\n### Current Skills:\n{skill_list_str}" + strict_instruction
        else:
            # Native Behavior: Do not inject skill list text, rely on SDK tools definition
            route_config.system_prompt = strict_instruction

        # 2. Get/Create Session (with state sync)
        wrapper = await self.session_manager.get_or_create(event.session_id, route_config, tools=sdk_tools)
        session = wrapper.sdk_session
        
        # 3. Handle Events (Accumulate turn data)
        turn_data = {
            "assistant_message": "",
            "tools_used": [],
            "error": None
        }
        done_event = asyncio.Event()

        def handle_event(event_obj: Any):
            e_type = event_obj.type.value if hasattr(event_obj.type, 'value') else str(event_obj.type)
            print(f"Captured event: {e_type}")
            
            if e_type == "assistant.message":
                # Some versions of Copilot SDK or LLMs prepend thought blocks.
                # We accumulate here, we will clean it at the end.
                turn_data["assistant_message"] += event_obj.data.content
                print(f"Assistant message received: {event_obj.data.content[:50]}...")
            elif e_type == "tool.execution_start":
                turn_data["tools_used"].append({
                    "name": event_obj.data.tool_name,
                    "args": event_obj.data.arguments,
                    "status": "running"
                })
                print(f"Tool execution started by SDK: {event_obj.data.tool_name}")
                if status_callback:
                    asyncio.create_task(status_callback(f"⚙️ 正在使用技能: {event_obj.data.tool_name}..."))
            elif e_type == "tool.execution_complete":
                # Find matching tool call and update status
                for t in turn_data["tools_used"]:
                    if t["name"] == event_obj.data.tool_name and t["status"] == "running":
                        t["status"] = "success"
                        t["result_summary"] = str(event_obj.data.result)[:200]
                        break
                print(f"Tool execution complete: {event_obj.data.tool_name}")
            elif e_type == "session.error":
                turn_data["error"] = event_obj.data.message
                print(f"SDK Error: {event_obj.data.message}")
                if status_callback:
                    asyncio.create_task(status_callback(f"❌ 執行發生錯誤: {event_obj.data.message}"))
                done_event.set()
            elif e_type == "session.idle":
                print("Session idle, finishing...")
                done_event.set()

        unsubscribe = session.on(handle_event)
        
        # 4. Send message
        await session.send(MessageOptions(prompt=event.content))
        
        # Wait
        await done_event.wait()
        
        unsubscribe()
        wrapper.turn_count += 1

        # Clean up any residual thought tags if present
        final_content = turn_data["assistant_message"]
        if "<think>" in final_content:
            final_content = re.sub(r'<think>.*?</think>', '', final_content, flags=re.DOTALL).strip()
        
        return AgentResponse(
            content=final_content,
            tool_calls=turn_data["tools_used"]
        )

    async def _process_tool_execution(self, session: Any, event_obj: Any, tool_calls: List[dict]):
        # Deprecated: Handled by SDK now
        pass
