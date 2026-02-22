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

        # 2. Read local memory and append to system_prompt BEFORE session creation.
        # ⚠️ 重要：記憶必須附加到 system_prompt，由 SDK 以 mode=replace 統一管理。
        # 嚴禁注入到 user_message，否則每輪都會往 session history 寫入，最終觸發 400 invalid_request_body。
        import json
        import os
        from src.config import settings
        storage_path = settings.SESSION_STORAGE_PATH
        memory_context = ""

        # --- Type 1: Long-term Facts ---
        facts_file = os.path.join(storage_path, "local_memory.json")
        if os.path.exists(facts_file):
            try:
                with open(facts_file, 'r', encoding='utf-8') as f:
                    facts_data = json.load(f)
                    if facts_data:
                        facts_str = ""
                        for k, v in facts_data.items():
                            if "session_summary" not in k and "latest_mechanic" not in k:
                                facts_str += f"- {k}: {v}\n"
                        if facts_str:
                            memory_context += "### [長期事實記憶 (Facts)]:\n" + facts_str
            except Exception as e:
                print(f"[Orchestrator] Error reading facts: {e}")

        # --- Type 2: Recent Events (Last 5) ---
        events_file = os.path.join(storage_path, "event_log.json")
        if os.path.exists(events_file):
            try:
                with open(events_file, 'r', encoding='utf-8') as f:
                    events_data = json.load(f)
                    if events_data and isinstance(events_data, list):
                        event_str = ""
                        for entry in events_data[-5:]:
                            ts = entry.get("timestamp", "")[:16].replace("T", " ")
                            event_str += f"- [{ts}] {entry.get('key')}: {entry.get('value')}\n"
                        if event_str:
                            memory_context += "\n### [近期事件紀錄 (Recent Events)]:\n" + event_str
            except Exception as e:
                print(f"[Orchestrator] Error reading events: {e}")

        if memory_context:
            memory_context += (
                "\n[Memory Instruction]: 你具備透過 local_memory 工具讀寫記憶的能力。\n"
                "- 請將永久性的偏好或事實存為 'fact' 類型 (local_memory.json)。\n"
                "- 請將工作階段摘要或暫時性的進度更新存為 'event' 類型 (event_log.json)。"
            )
            # 附加到 system_prompt，SDK 使用 mode=replace 更新，不會污染 session history
            route_config.system_prompt = (route_config.system_prompt or "") + "\n\n" + memory_context

        # 3. Get/Create Session (system_prompt now includes fresh memory context)
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

        # 5. User message — clean, no context injection.
        # Memory context is already in system_prompt (updated at step 2, managed by SDK with mode=replace).
        # DO NOT inject memory here — it would accumulate in session history and cause 400 overflow.
        injected_message = event.content

        # Optionally passing instructions here if SDK allows, but prompt is strictly user msg.
        # 🛡️ Session Auto-Recovery: If the Copilot SDK subprocess crashes (OSError / BrokenPipe),
        # we transparently invalidate the dead session and retry once with a new session.
        async def send_with_recovery():
            nonlocal session, wrapper, done_event, turn_data
            try:
                await session.send(MessageOptions(prompt=injected_message))
                await done_event.wait()
                unsubscribe()
            except (OSError, BrokenPipeError) as pipe_err:
                print(f"[Orchestrator] ⚠️ SDK pipe/subprocess failure detected: {pipe_err}")
                print("[Orchestrator] Invalidating broken session and retrying with a fresh one...")
                unsubscribe()  # Detach the dead event listener
                
                # Invalidate the broken session from cache and mapping
                self.session_manager.invalidate_session(event.session_id, route_config)
                
                # Reset turn data for the retry
                turn_data["assistant_message"] = ""
                turn_data["tools_used"] = []
                turn_data["error"] = None
                done_event.clear()
                
                # Create a brand new session
                new_wrapper = await self.session_manager.get_or_create(event.session_id, route_config, tools=sdk_tools)
                wrapper = new_wrapper
                session = new_wrapper.sdk_session
                
                # Re-subscribe to events on new session
                self.session_manager._sessions[event.session_id] = new_wrapper
                unsubscribe_new = session.on(handle_event)
                
                # Retry send
                print("[Orchestrator] Retrying message on new session...")
                await session.send(MessageOptions(prompt=injected_message))
                await done_event.wait()
                unsubscribe_new()
                return
                
        await send_with_recovery()
        
        # 🔄 Session History Reset: If the SDK returns 400/invalid_request_body,
        # it means the session history is too long. Invalidate and retry on a fresh session.
        error_msg = turn_data.get("error", "") or ""
        is_history_overflow = (
            "invalid_request_body" in error_msg or 
            ("400" in error_msg and not turn_data["assistant_message"])
        )
        if is_history_overflow:
            print(f"[Orchestrator] ⚠️ Session history overflow detected (400). Resetting session...")
            self.session_manager.invalidate_session(event.session_id, route_config)
            
            # Reset turn_data for fresh retry
            turn_data["assistant_message"] = ""
            turn_data["tools_used"] = []
            turn_data["error"] = None
            done_event.clear()
            
            # Create a fresh session
            new_wrapper = await self.session_manager.get_or_create(event.session_id, route_config, tools=sdk_tools)
            wrapper = new_wrapper
            session = new_wrapper.sdk_session
            unsubscribe_new = session.on(handle_event)
            
            # Inform the user the context was cleared  
            context_cleared_message = (
                "[Note: 由於對話歷史過長，系統已自動清除歷史並開始新的對話。] \n\n"
                + injected_message
            )
            print("[Orchestrator] Retrying with cleared session history...")
            await session.send(MessageOptions(prompt=context_cleared_message))
            await done_event.wait()
            unsubscribe_new()
        
        wrapper.turn_count += 1

        # 6. Post-process and Persist Session Summary to [event_log.json]
        from datetime import datetime, timedelta
        final_content = turn_data["assistant_message"]
        if "<think>" in final_content:
            final_content = re.sub(r'<think>.*?</think>', '', final_content, flags=re.DOTALL).strip()
        
        # ── 自動持久化 Session 摘要到事件紀錄 ──
        if final_content and len(final_content) > 10:
            try:
                events_file = os.path.join(storage_path, "event_log.json")
                events_data = []
                if os.path.exists(events_file):
                    with open(events_file, 'r', encoding='utf-8') as f:
                        events_data = json.load(f)
                        if not isinstance(events_data, list):
                            events_data = []

                # Create summary entry
                summary_text = final_content[:200]
                if len(final_content) > 200:
                    summary_text += "..."
                
                new_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "key": f"session_summary_{event.session_id}",
                    "value": summary_text
                }
                events_data.append(new_entry)

                # Cleanup: Max 50, Max 7 days
                threshold = datetime.now() - timedelta(days=7)
                filtered_events = []
                for e in events_data:
                    try:
                        ts = datetime.fromisoformat(e.get("timestamp", ""))
                        if ts > threshold:
                            filtered_events.append(e)
                    except:
                        filtered_events.append(e) # Keep if timestamp missing
                
                # Keep last 50
                events_data = filtered_events[-50:]

                with open(events_file, 'w', encoding='utf-8') as f:
                    json.dump(events_data, f, ensure_ascii=False, indent=2)
                print(f"[Orchestrator] Session summary persisted to event_log.json for {event.session_id}")
            except Exception as e:
                print(f"[Orchestrator] Failed to save session summary: {e}")

        return AgentResponse(
            content=final_content,
            tool_calls=turn_data["tools_used"]
        )

    async def _process_tool_execution(self, session: Any, event_obj: Any, tool_calls: List[dict]):
        # Deprecated: Handled by SDK now
        pass
