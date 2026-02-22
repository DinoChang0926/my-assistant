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
        
        # Filter tools based on Sub-agent Role definition
        if route_config.role and route_config.role.allowed_tools:
            allowed_names = set(route_config.role.allowed_tools)
            base_tools = [t for t in base_tools if t.name in allowed_names]
            print(f"[Orchestrator] Filtering tools for Sub-agent role '{route_config.role.role_id}': {allowed_names}")
        
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
                        
                        # 將推播函數注入到工具參數中
                        if status_callback:
                            args["status_callback"] = status_callback
                            
                        result_data = await t_instance.execute(**args)
                        
                        result_str = str(result_data)
                        # 強制截斷工具回傳的字串長度，防範 Payload 堆疊
                        # 若回傳過大，即使單次未爆掉，數次對話後仍會觸發 400 invalid_request_body
                        MAX_LENGTH = 4000
                        if len(result_str) > MAX_LENGTH:
                            result_str = result_str[:MAX_LENGTH] + "\n...(truncated due to length limits)"
                            
                        return {
                            "resultType": "success",
                            "textResultForLlm": result_str
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
        # Grouping by category; truncate descriptions to save token budget
        categories = {}
        for t in base_tools:
            cat = getattr(t, 'category', 'general')
            if cat not in categories:
                categories[cat] = []
            # Truncate description to 60 chars to keep prompt compact
            short_desc = t.description[:60].replace('\n', ' ')
            if len(t.description) > 60:
                short_desc += "..."
            categories[cat].append(f"  - {t.name}: {short_desc}")
        
        skill_list_groups = []
        for cat, skills in sorted(categories.items()):
            group_str = f"[{cat.upper()}] " + " | ".join(s.strip("  - ") for s in skills)
            skill_list_groups.append(group_str)
        
        skill_list_str = "\n".join(skill_list_groups)
        if not skill_list_str:
            skill_list_str = "(No unlocked skills available, please use create_tool to create one)"

        # 追加嚴格指令，禁止輸出思考過程與冗餘解釋
        strict_instruction = (
            "\n\n[CRITICAL]: 當你需要呼叫工具 (例如 local_memory) 時，請「直接」呼叫工具，絕對不要在訊息中輸出你的思考過程 (Chain of Thought)、"
            "自我解釋、或是諸如「將從本機記憶讀取...」、「將把XXX儲存...」的預告動作說明。請默默地在背景使用工具，處理完畢後直接給使用者最終、精簡、自然的對話回應即可。"
        )

        current_prompt = route_config.system_prompt
        if current_prompt:
            if "{skill_list}" in current_prompt:
                 route_config.system_prompt = current_prompt.replace("{skill_list}", skill_list_str) + strict_instruction
            else:
                 # Inject skill list and strict instructions if not explicitly placed
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
            import logging
            logger = logging.getLogger("orchestrator")
            e_type = event_obj.type.value if hasattr(event_obj.type, 'value') else str(event_obj.type)
            logger.debug(f"Captured event: {e_type}")
            
            if e_type == "assistant.message":
                turn_data["assistant_message"] = event_obj.data.content
                logger.debug(f"Assistant message received: {event_obj.data.content[:50]}...")
            elif e_type == "tool.execution_start":
                turn_data["tools_used"].append({
                    "name": event_obj.data.tool_name,
                    "args": event_obj.data.arguments,
                    "status": "running"
                })
                print(f"[SDK Tool Execution Started]: {event_obj.data.tool_name}")
            elif e_type == "tool.execution_complete":
                # Find matching tool call and update status
                for t in turn_data["tools_used"]:
                    if t["name"] == event_obj.data.tool_name and t["status"] == "running":
                        t["status"] = "success"
                        t["result_summary"] = str(event_obj.data.result)[:200]
                        break
                logger.debug(f"Tool execution complete: {event_obj.data.tool_name}")
            elif e_type == "session.error":
                turn_data["error"] = event_obj.data.message
                print(f"[SDK Error]: {event_obj.data.message}")
                done_event.set()
            elif e_type == "session.idle":
                logger.debug("Session idle, finishing...")
                done_event.set()

        unsubscribe = session.on(handle_event)
        
        # 4. Read local memory for Context Injection
        import json
        import os
        from src.config import settings

        user_facts = ""
        session_summary = ""
        memory_file = os.path.join(settings.SESSION_STORAGE_PATH, "local_memory.json")
        
        memory_data = {}
        try:
            if os.path.exists(memory_file):
                with open(memory_file, 'r', encoding='utf-8') as f:
                    memory_data = json.load(f)
                    if memory_data:
                        session_key = f"session_summary_{event.session_id}"
                        for k, v in memory_data.items():
                            if k == session_key:
                                # Format session summary (stored as list of events joined by ||||)
                                items = [i.strip() for i in v.split("||||") if i.strip()]
                                if items:
                                    session_summary = "\n".join(f"  - {i}" for i in items)
                            else:
                                user_facts += f"- {k}: {v}\n"
        except Exception as e:
            print(f"[Orchestrator] Error reading local memory: {e}")

        memory_context = ""
        if user_facts:
            memory_context += "### [使用者長期記憶 (User Persistent Memory)]:\n" + user_facts
        if session_summary:
            memory_context += "\n### [上次對話進度摘要 (Session History Summary) - 這對維持上下文極度重要]:\n" + session_summary

        # 5. Prepare the message payload.
        # 我們將記憶附加到使用者的輸入中，但【絕對不要在這裡插入 System Prompt】。
        # 因為把 System Prompt 放進每輪的 User Message 會導致 Session History 隨對話次數指數級膨脹，
        # 最終引發 Copilot SDK 報出 400 invalid_request_body。
        # System Prompt 已經在 _get_or_create 建立 session 時作為 system_instructions 傳過一次了。
        if memory_context:
            injected_message = f"[System Context]:{memory_context}\n\n[User Message]:\n{event.content}"
        else:
            injected_message = event.content

        # Optionally passing instructions here if SDK allows, but prompt is strictly user msg.
        await session.send(MessageOptions(prompt=injected_message))
        
        # Wait
        await done_event.wait()
        
        unsubscribe()
        wrapper.turn_count += 1

        # 6. Post-process and Persist Session Summary
        from datetime import datetime
        final_content = turn_data["assistant_message"]
        if "<think>" in final_content:
            final_content = re.sub(r'<think>.*?</think>', '', final_content, flags=re.DOTALL).strip()
        
        # ── 自動持久化 Session 摘要 ──
        if final_content and len(final_content) > 10:
            session_key = f"session_summary_{event.session_id}"
            # 抓取回應的一小段作為摘要 (在此可以做得更聰明，比如由 LLM 摘要，但我們先用簡單版)
            summary_entry = f"[{datetime.now().strftime('%m/%d %H:%M')}] {final_content[:200]}"
            if len(final_content) > 200:
                summary_entry += "..."
                
            existing_str = memory_data.get(session_key, "")
            summary_list = [s.strip() for s in existing_str.split("||||") if s.strip()]
            # 只保留最近 3 輪
            summary_list = summary_list[-2:] 
            summary_list.append(summary_entry)
            
            memory_data[session_key] = "||||".join(summary_list)
            
            try:
                with open(memory_file, 'w', encoding='utf-8') as f:
                    json.dump(memory_data, f, ensure_ascii=False, indent=2)
                print(f"[Orchestrator] Session summary persisted for {event.session_id}")
            except Exception as e:
                print(f"[Orchestrator] Failed to save session summary: {e}")

        return AgentResponse(
            content=final_content,
            tool_calls=turn_data["tools_used"]
        )

    async def _process_tool_execution(self, session: Any, event_obj: Any, tool_calls: List[dict]):
        # Deprecated: Handled by SDK now
        pass
