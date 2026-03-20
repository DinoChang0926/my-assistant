import asyncio
import copy
import json
import os
import logging
from typing import Any, List, Callable, Awaitable, Optional
from src.core.events import AgentEvent, AgentResponse
from src.core.interfaces import RouteConfig
from src.memory.manager import SessionManager
from src.tools.registry import ToolRegistry
from src.config import settings

logger = logging.getLogger("orchestrator")

class TaskOrchestrator:
    """Coordinates the execution flow between Memory, SDK, and Tools."""
    
    def __init__(self, session_manager: SessionManager, tool_registry: ToolRegistry):
        self.session_manager = session_manager
        self.tool_registry = tool_registry

    def _build_tool_catalog(self, sdk_tools: List[Any]) -> str:
        """Helper to build a compact tool catalog string for the system prompt."""
        sdk_tool_names = [getattr(st, 'name', '') for st in sdk_tools]
        
        tool_catalog_str = " | ".join(filter(None, sdk_tool_names))

        return (
            "\n\n[CRITICAL]: 不要輸出思考過程，直接呼叫工具即可。\n"
            "### Meta-Tools (Local):\n" + tool_catalog_str + "\n"
            "### App-Tools (MCP):\n"
            "所有原子工具與應用程式邏輯均已由系統底層的 MCP 伺服器 (FastMCP) 啟動，請直接呼叫或詢問使用者有哪些工具可用。"
        )

    async def execute(self, event: AgentEvent, original_route_config: RouteConfig, status_callback: Optional[Callable[[str], Awaitable[None]]] = None) -> AgentResponse:
        # 0. Hot Reload Tools
        await self.tool_registry.refresh()

        # 1. Prepare copy to avoid global mutation
        route_config = copy.copy(original_route_config)
        original_system_prompt = route_config.system_prompt or ""

        # 1.5 Build SDK tools via registry + inject Tool Catalog
        sdk_tools = self.tool_registry.to_sdk_tools(route_config, status_callback, event.session_id)
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
        try:
            wrapper = await self.session_manager.get_or_create(event.session_id, route_config, tools=sdk_tools)
        except RuntimeError as supervisor_err:
            # 🛡️ Supervisor 不可侵犯原則觸發：session 無法恢復也拒絕重建
            logger.error(f"[Orchestrator] 🚨 Supervisor session protection triggered: {supervisor_err}")
            return AgentResponse(
                content="系統偵測到對話連線異常，但為保護您的歷史記憶，已拒絕重建對話。請稍後再試或重新啟動服務。",
                tool_calls=[]
            )

        # 4. Send and Wait
        content = ""
        try:
            response = await asyncio.wait_for(
                wrapper.sdk_session.send_and_wait({"prompt": event.content}),
                timeout=120.0
            )
            content = response.data.content if response else ""
        except (OSError, BrokenPipeError) as pipe_err:
            logger.warning(f"[Orchestrator] ⚠️ SDK pipe failure: {pipe_err}. Resetting session (force-recreate)...")
            self.session_manager.invalidate(event.session_id, route_config, force_recreate=True)
            content = "系統管線異常，已重新啟動服務，請再試一次。"
        except asyncio.TimeoutError:
            logger.warning("[Orchestrator] ⚠️ Session wait timeout!")
            content = "API 回應逾時，請稍後再試。"
        except Exception as e:
            err_str = str(e)
            if "invalid_request_body" in err_str or "400" in err_str:
                logger.warning("[Orchestrator] ⚠️ Overflow reset.")
                self.session_manager.invalidate(event.session_id, route_config)
                content = "[Note: 由於對話歷史過長，系統已自動為您重啟全新對話，請重新輸入。]"
            else:
                logger.error(f"[Orchestrator] Unexpected error: {e}")
                content = "系統發生未預期的錯誤，請稍後再試。"

        wrapper.turn_count += 1

        # 5. Post-process: persist summary
        if content and len(content) > 10:
            try:
                events_file = os.path.join(storage_path, "event_log.json")
                # (Summary persistence logic...)
            except:
                pass

        return AgentResponse(
            content=content,
            tool_calls=[]
        )
