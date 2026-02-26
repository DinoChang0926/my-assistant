import asyncio
import re
import copy
import json
import os
import logging
from datetime import datetime
from typing import Any, List, Callable, Awaitable, Optional
from src.core.events import AgentEvent, AgentResponse
from src.core.interfaces import RouteConfig
from src.memory.manager import SessionManager
from src.tools.registry import ToolRegistry
from src.brain.prompts import SKILL_ACQUISITION_PROMPT
from src.config import settings
from copilot import MessageOptions

logger = logging.getLogger("orchestrator")

class TaskOrchestrator:
    """Coordinates the execution flow between Memory, SDK, and Tools."""
    
    def __init__(self, session_manager: SessionManager, tool_registry: ToolRegistry):
        self.session_manager = session_manager
        self.tool_registry = tool_registry

    def _build_tool_catalog(self, sdk_tools: List[Any]) -> str:
        """Helper to build a compact tool catalog string for the system prompt."""
        all_tools = list(self.tool_registry._tools.values())
        catalog_by_cat = {}
        for t in all_tools:
            cat = getattr(t, 'category', 'general')
            if cat not in catalog_by_cat: catalog_by_cat[cat] = []
            status = "✅ loaded" if any(t.name == st.name for st in sdk_tools) else "⬇️ inactive (use activate_tools)"
            catalog_by_cat[cat].append(f"{t.name} ({status})")

        catalog_lines = [f"[{cat.upper()}] " + " | ".join(items) for cat, items in sorted(catalog_by_cat.items())]
        tool_catalog_str = "\n".join(catalog_lines)

        return (
            "\n\n[CRITICAL]: 不要輸出思考過程，直接呼叫工具即可。\n"
            "### Tool Catalog (Index):\n" + tool_catalog_str + "\n"
            "如果你需要 'inactive' 的工具類別，請先呼叫 `activate_tools(categories=['category_name'])`。"
        )

    async def execute(self, event: AgentEvent, original_route_config: RouteConfig, status_callback: Optional[Callable[[str], Awaitable[None]]] = None) -> AgentResponse:
        # 0. Hot Reload Tools
        await self.tool_registry.refresh()

        # 1. Prepare copy to avoid global mutation
        route_config = copy.copy(original_route_config)
        active_categories = set(route_config.role.allowed_categories) if route_config.role else set()
        original_system_prompt = route_config.system_prompt or ""
        
        def get_filtered_sdk_tools(categories_filter):
            filtered_base_tools = list(self.tool_registry._tools.values())
            if categories_filter:
                filtered_base_tools = [t for t in filtered_base_tools if getattr(t, 'category', 'general') in categories_filter]
            
            if route_config.role and route_config.role.allowed_tools:
                allowed_names = set(route_config.role.allowed_tools)
                filtered_base_tools = [t for t in filtered_base_tools if t.name in allowed_names]
            
            from copilot.types import Tool, ToolInvocation, ToolResult
            res_sdk_tools = []
            for tool in filtered_base_tools:
                def make_handler(t_instance):
                    async def handler(invocation: ToolInvocation) -> ToolResult:
                        try:
                            args = invocation.get("arguments", {}) or {}
                            if status_callback: args["status_callback"] = status_callback
                            args["caller_session_id"] = event.session_id
                            result_data = await t_instance.execute(**args)
                            return {
                                "resultType": "success",
                                "textResultForLlm": str(result_data)[:4000]
                            }
                        except Exception as e:
                            return {"resultType": "failure", "error": str(e)}
                    return handler

                # 🛡️ Defense against "Cannot read properties of undefined (reading 'map')"
                # The SDK expects 'properties' to exist on 'object' types even if empty.
                safe_params = copy.deepcopy(tool.parameters) if tool.parameters else {"type": "object"}
                if safe_params.get("type") == "object" and "properties" not in safe_params:
                    safe_params["properties"] = {}

                res_sdk_tools.append(Tool(
                    name=tool.name,
                    description=tool.description,
                    parameters=safe_params,
                    handler=make_handler(tool)
                ))
            return res_sdk_tools, filtered_base_tools

        sdk_tools, _ = get_filtered_sdk_tools(active_categories)
        
        # 1.5 Inject Initial Tool Catalog
        route_config.system_prompt = original_system_prompt + self._build_tool_catalog(sdk_tools)

        # 2. Read local memory and append to system_prompt BEFORE session creation.
        storage_path = settings.SESSION_STORAGE_PATH
        memory_parts = []

        def _read_json_file(path: str):
            """Synchronous JSON reader, intended for asyncio.to_thread calls."""
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)

        facts_file = os.path.join(storage_path, "local_memory.json")
        if os.path.exists(facts_file):
            try:
                facts_data = await asyncio.to_thread(_read_json_file, facts_file)
                if facts_data:
                    for k, v in list(facts_data.items())[:10]:
                        if "session_summary" not in k and "latest_mechanic" not in k:
                            memory_parts.append(f"{k}={str(v)[:60]}")
            except Exception as e:
                logger.info(f"[Orchestrator] Error reading facts: {e}")

        events_file = os.path.join(storage_path, "event_log.json")
        if os.path.exists(events_file):
            try:
                events_data = await asyncio.to_thread(_read_json_file, events_file)
                if events_data and isinstance(events_data, list):
                    for entry in events_data[-2:]:
                        ts = entry.get("timestamp", "")[:10]
                        val = str(entry.get('value', ''))[:80]
                        memory_parts.append(f"[{ts}]{entry.get('key')}:{val}")
            except Exception as e:
                logger.info(f"[Orchestrator] Error reading events: {e}")

        if memory_parts:
            compact_memory = "[MEM] " + " | ".join(memory_parts)
            if len(compact_memory) > 600:
                compact_memory = compact_memory[:597] + "..."
            compact_memory += "\n[MEM-RULE] 上方記憶已是最新，勿再呼叫 local_memory 讀取。"
            route_config.system_prompt += "\n\n" + compact_memory

        # 3. Get/Create Session
        wrapper = await self.session_manager.get_or_create(event.session_id, route_config, tools=sdk_tools)
        session = wrapper.sdk_session
        
        turn_data = {
            "assistant_message": "",
            "tools_used": [],
            "error": None
        }
        done_event = asyncio.Event()

        def handle_event(event_obj: Any):
            e_type = event_obj.type.value if hasattr(event_obj.type, 'value') else str(event_obj.type)
            logger.info(f"[SDK Event Debug] type={e_type}, data={getattr(event_obj, 'data', None)}")
            
            if e_type == "assistant.message":
                turn_data["assistant_message"] = event_obj.data.content
            elif e_type == "tool.execution_start":
                turn_data["tools_used"].append({
                    "name": event_obj.data.tool_name,
                    "args": event_obj.data.arguments,
                    "status": "running"
                })
            elif e_type == "tool.execution_complete":
                res_val = str(event_obj.data.result)
                for t in turn_data["tools_used"]:
                    if t["name"] == event_obj.data.tool_name and t["status"] == "running":
                        t["status"] = "success"
                        t["result_summary"] = res_val[:200]
                        break
                
                if "upgrade_signal" in res_val:
                    try:
                        result_dict = json.loads(res_val) if res_val.startswith('{') else {}
                        if result_dict.get("status") == "upgrade_signal":
                            cats = result_dict.get("requested_categories", [])
                            turn_data["upgrade_requested"] = cats
                    except (json.JSONDecodeError, Exception):
                        pass
            elif e_type == "session.error":
                turn_data["error"] = event_obj.data.message
                done_event.set()
            elif e_type == "session.idle":
                done_event.set()

        unsubscribe = session.on(handle_event)
        injected_message = event.content

        # 🛡️ Session Auto-Recovery (Pipe Errors Only)
        async def send_with_recovery():
            nonlocal session, wrapper, done_event, turn_data
            try:
                await asyncio.wait_for(session.send(MessageOptions(prompt=injected_message)), timeout=30.0)
                await asyncio.wait_for(done_event.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                logger.info("[Orchestrator] ⚠️ Session wait timeout! Forcing release.")
                turn_data["error"] = "API 回應逾時"
            except (OSError, BrokenPipeError) as pipe_err:
                logger.info(f"[Orchestrator] ⚠️ SDK pipe failure: {pipe_err}. Soft-resetting session...")
                # 🔄 Soft invalidate: clear memory but keep UUID on disk for resumption
                self.session_manager.soft_invalidate(event.session_id, route_config)
                wrapper = await self.session_manager.get_or_create(event.session_id, route_config, tools=sdk_tools)
                session = wrapper.sdk_session
                turn_data["error"] = "系統管線異常，已重新啟動服務，請再試一次。"
                
        await send_with_recovery()
        unsubscribe()
        
        # 🔄 Session History Reset (400)
        error_msg = turn_data.get("error") or ""
        if "invalid_request_body" in error_msg or ("400" in error_msg and not turn_data["assistant_message"]):
            logger.info("[Orchestrator] ⚠️ Overflow reset.")
            self.session_manager.invalidate_session(event.session_id, route_config)
            wrapper = await self.session_manager.get_or_create(event.session_id, route_config, tools=sdk_tools)
            
            turn_data["assistant_message"] = "[Note: 由於對話歷史過長，系統已自動為您重啟全新對話，請重新輸入。]"
            turn_data["error"] = None
            turn_data["tools_used"] = []
            
        wrapper.turn_count += 1
        
        # 6. Post-process
        final_content = turn_data["assistant_message"]
        if "<think>" in final_content:
            final_content = re.sub(r'<think>.*?</think>', '', final_content, flags=re.DOTALL).strip()
        
        # ── 自動持久化摘要 ──
        if final_content and len(final_content) > 10:
             try:
                events_file = os.path.join(storage_path, "event_log.json")
                # (Summary persistence logic...)
             except: pass

        return AgentResponse(
            content=final_content,
            tool_calls=turn_data["tools_used"]
        )

    async def _process_tool_execution(self, session: Any, event_obj: Any, tool_calls: List[dict]):
        pass
