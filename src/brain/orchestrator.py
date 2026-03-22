import asyncio
import copy
import json
import os
import logging
import urllib.request
import urllib.error
from datetime import datetime
from typing import Any, List, Callable, Awaitable, Optional
from src.core.events import AgentEvent, AgentResponse
from src.core.interfaces import RouteConfig
from src.memory.manager import SessionManager, SessionWrapper
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
            "[RUNTIME-RULE]: 任何『工具不可用 / 進入降級模式 / 儲存失敗』敘述都必須基於當輪可驗證證據，"
            "不可沿用前一輪假設或記憶推測。\n"
            "[RUNTIME-RULE]: 若工具可用，優先直接執行並回報結果；若執行失敗，必須說明是本輪失敗而非持續狀態。\n"
            "### Meta-Tools (Local):\n" + tool_catalog_str + "\n"
            "### App-Tools (MCP):\n"
            "所有原子工具與應用程式邏輯均已由系統底層的 MCP 伺服器 (FastMCP) 啟動，請直接呼叫或詢問使用者有哪些工具可用。"
        )

    def _attach_turn_event_logger(
        self,
        sdk_session: Any,
        event_id: str,
        phase: str,
    ) -> Callable[[], None]:
        """Attach per-turn event logger and return an unsubscribe callable."""

        def _safe_event_attr(evt: Any, name: str, default: str = "") -> str:
            value = getattr(evt, name, default)
            return str(value) if value is not None else default

        def _safe_data_attr(data: Any, *names: str) -> str:
            for n in names:
                if hasattr(data, n):
                    value = getattr(data, n)
                    if value is not None:
                        return str(value)
            return ""

        def _on_event(evt: Any):
            evt_type = _safe_event_attr(evt, "type", "unknown")
            data = getattr(evt, "data", None)

            if evt_type in ("tool.execution_start", "tool.call_start"):
                tool_name = _safe_data_attr(data, "tool_name", "name") or "unknown_tool"
                logger.info(
                    f"[TurnEvent][{event_id}][{phase}] tool.start name={tool_name}"
                )
            elif evt_type in ("tool.execution_end", "tool.call_end"):
                tool_name = _safe_data_attr(data, "tool_name", "name") or "unknown_tool"
                result_type = _safe_data_attr(data, "result_type", "resultType", "status") or "unknown"
                logger.info(
                    f"[TurnEvent][{event_id}][{phase}] tool.end name={tool_name} result={result_type}"
                )
            elif evt_type == "session.idle":
                logger.info(f"[TurnEvent][{event_id}][{phase}] session.idle")
            elif evt_type == "session.error":
                err_msg = _safe_data_attr(data, "message", "error", "detail")
                logger.warning(
                    f"[TurnEvent][{event_id}][{phase}] session.error message={err_msg}"
                )

        unsubscribe = None
        try:
            unsubscribe = sdk_session.on(_on_event)
        except Exception as hook_err:
            logger.warning(
                f"[TurnEvent][{event_id}][{phase}] attach_failed "
                f"{type(hook_err).__name__}: {hook_err}"
            )

        def _noop_unsubscribe():
            return None

        if callable(unsubscribe):
            return unsubscribe
        return _noop_unsubscribe

    def _extract_memo_content(self, text: str) -> Optional[str]:
        """Extract memo content from common Chinese prompt patterns."""
        if not text:
            return None

        normalized = text.replace("\n", " ").strip()
        triggers = [
            "請幫我寫一筆新的備忘錄：",
            "請幫我寫一筆新的備忘錄:",
            "寫一筆新的備忘錄：",
            "寫一筆新的備忘錄:",
            "新增備忘錄：",
            "新增備忘錄:",
        ]
        for t in triggers:
            if t in normalized:
                after = normalized.split(t, 1)[1].strip()
                return after or None
        return None

    async def _persist_memo_content(self, memo: str) -> str:
        storage_path = settings.SESSION_STORAGE_PATH
        facts_file = os.path.join(storage_path, "local_memory.json")

        def _write_fact() -> str:
            os.makedirs(storage_path, exist_ok=True)
            data = {}
            if os.path.exists(facts_file):
                try:
                    with open(facts_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data = loaded
                except Exception:
                    data = {}

            key = f"memo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            data[key] = memo
            with open(facts_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return key

        memo_key = await asyncio.to_thread(_write_fact)
        return memo_key

    @staticmethod
    def _contains_tool_unavailable_claim(text: str) -> bool:
        normalized = (text or "").lower()
        markers = [
            "降級模式",
            "工具暫不可用",
            "mcp / 工具暫不可用",
            "mcp/工具暫不可用",
            "無法把它寫入長期記憶",
            "儲存服務回傳錯誤",
            "tool unavailable",
            "degraded mode",
        ]
        return any(m in normalized for m in markers)

    async def _is_mcp_runtime_healthy(self, timeout_sec: float = 1.2) -> bool:
        sse_url = "http://127.0.0.1:8001/sse"
        status_url = "http://127.0.0.1:8001/status"

        def _probe() -> bool:
            req = urllib.request.Request(sse_url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                if resp.status != 200:
                    return False

            try:
                req2 = urllib.request.Request(status_url, method="GET")
                with urllib.request.urlopen(req2, timeout=timeout_sec) as resp2:
                    if resp2.status != 200:
                        return True  # fallback for older MCP without /status contract
                    payload = json.loads(resp2.read().decode("utf-8"))
                    return payload.get("status") == "ok"
            except Exception:
                return True

        try:
            return await asyncio.to_thread(_probe)
        except Exception:
            return False

    async def _retry_response_with_runtime_facts(
        self,
        wrapper: SessionWrapper,
        event: AgentEvent,
        previous_content: str,
        timeout_sec: float = 30.0,
    ) -> Optional[str]:
        retry_prompt = (
            "[系統校正任務]\n"
            "你上一則回覆可能把狀態判斷為『工具不可用/降級』，"
            "但即時探測顯示 MCP 目前健康可用。\n"
            "請基於『當輪可驗證事實』重寫最終回覆，保留原本語氣與任務脈絡，"
            "不要提及本段校正流程。\n"
            "若仍需回報失敗，必須明確標示為『本輪執行失敗』，"
            "不可宣告為長期持續不可用。\n\n"
            f"[使用者原訊息]\n{event.content}\n\n"
            f"[你上一則回覆]\n{previous_content}"
        )

        retry_unsubscribe = self._attach_turn_event_logger(
            wrapper.sdk_session,
            event.event_id,
            phase="calibration-retry",
        )
        try:
            retry_response = await asyncio.wait_for(
                wrapper.sdk_session.send_and_wait({"prompt": retry_prompt}),
                timeout=timeout_sec,
            )
            retry_content = retry_response.data.content if retry_response else ""
            return retry_content or None
        except Exception as retry_err:
            logger.warning(
                "[ResponseCalibrator] model retry failed: "
                f"{type(retry_err).__name__}: {retry_err}"
            )
            return None
        finally:
            try:
                retry_unsubscribe()
            except Exception as unhook_err:
                logger.warning(
                    f"[TurnEvent][{event.event_id}][calibration-retry] unsubscribe_failed "
                    f"{type(unhook_err).__name__}: {unhook_err}"
                )

    async def _calibrate_high_risk_response(
        self,
        content: str,
        wrapper: SessionWrapper,
        event: AgentEvent,
    ) -> str:
        if not self._contains_tool_unavailable_claim(content):
            return content

        healthy = await self._is_mcp_runtime_healthy(timeout_sec=1.2)
        if not healthy:
            return content

        retried = await self._retry_response_with_runtime_facts(
            wrapper=wrapper,
            event=event,
            previous_content=content,
            timeout_sec=30.0,
        )
        if retried:
            logger.info("[ResponseCalibrator] Replaced response with model self-corrected retry.")
            return retried

        logger.warning(
            "[ResponseCalibrator] Corrected possible false tool-unavailable claim "
            "because runtime MCP probe is healthy."
        )
        return (
            content
            + "\n\n"
            + "[系統校正] 即時檢測顯示 MCP/工具目前可用。"
              "若你要我立即執行儲存，我會直接嘗試並回報本輪真實結果。"
        )

    async def _persist_memo_fallback(self, raw_text: str) -> Optional[str]:
        """Directly persist memo to local_memory.json as a last-resort fallback."""
        memo = self._extract_memo_content(raw_text)
        if not memo:
            return None

        memo_key = await self._persist_memo_content(memo)
        return f"已幫你寫入新的備忘錄（{memo_key}）：{memo}"

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
        role_id = route_config.role.role_id if route_config.role else "default"
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
        primary_unsubscribe = self._attach_turn_event_logger(
            wrapper.sdk_session,
            event.event_id,
            phase="primary",
        )
        try:
            response = await asyncio.wait_for(
                wrapper.sdk_session.send_and_wait({"prompt": event.content}),
                timeout=120.0
            )
            content = response.data.content if response else ""
        except (OSError, BrokenPipeError) as pipe_err:
            err_text = str(pipe_err)
            err_lower = err_text.lower()
            is_idle_timeout = ("session.idle" in err_lower and "timeout" in err_lower)

            if role_id == "supervisor" and is_idle_timeout:
                logger.warning(
                    "[Orchestrator] ⚠️ Supervisor session idle-timeout detected. "
                    "Invalidating cache and retrying once with normal tools."
                )
                self.session_manager.invalidate(event.session_id, route_config, force_recreate=False)
                try:
                    recovered_wrapper = await self.session_manager.get_or_create(
                        event.session_id,
                        route_config,
                        tools=sdk_tools,
                    )
                    recovered_unsubscribe = self._attach_turn_event_logger(
                        recovered_wrapper.sdk_session,
                        event.event_id,
                        phase="recovered-after-idle",
                    )
                    try:
                        recovered_response = await asyncio.wait_for(
                            recovered_wrapper.sdk_session.send_and_wait({"prompt": event.content}),
                            timeout=45.0,
                        )
                    finally:
                        try:
                            recovered_unsubscribe()
                        except Exception as unhook_err:
                            logger.warning(
                                f"[TurnEvent][{event.event_id}][recovered-after-idle] unsubscribe_failed "
                                f"{type(unhook_err).__name__}: {unhook_err}"
                            )
                    content = recovered_response.data.content if recovered_response else ""
                except Exception as recovered_err:
                    logger.warning(
                        "[Orchestrator] ⚠️ Retry after idle-timeout failed: "
                        f"{type(recovered_err).__name__}: {repr(recovered_err)}"
                    )
                    memo_fallback = await self._persist_memo_fallback(event.content)
                    if memo_fallback:
                        content = memo_fallback
                    else:
                        content = "系統對話剛發生逾時，已保留歷史。請稍後再試。"
            else:
                logger.warning(f"[Orchestrator] ⚠️ SDK pipe failure: {pipe_err}. Resetting session (force-recreate)...")
                force_recreate = role_id != "supervisor"
                self.session_manager.invalidate(event.session_id, route_config, force_recreate=force_recreate)
                if role_id == "supervisor":
                    content = "系統管線異常，已保留對話歷史。請再試一次。"
                else:
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
            elif "session not found" in err_str.lower():
                logger.warning(
                    "[Orchestrator] Session missing on SDK side. "
                    "Invalidating cache and retrying once."
                )
                self.session_manager.invalidate(
                    event.session_id,
                    route_config,
                    force_recreate=True,
                )
                try:
                    wrapper = await self.session_manager.get_or_create(
                        event.session_id,
                        route_config,
                        tools=sdk_tools,
                    )
                    retry_unsubscribe = self._attach_turn_event_logger(
                        wrapper.sdk_session,
                        event.event_id,
                        phase="recovered",
                    )
                    try:
                        retry_response = await asyncio.wait_for(
                            wrapper.sdk_session.send_and_wait({"prompt": event.content}),
                            timeout=45.0,
                        )
                    finally:
                        try:
                            retry_unsubscribe()
                        except Exception as unhook_err:
                            logger.warning(
                                f"[TurnEvent][{event.event_id}][recovered] unsubscribe_failed "
                                f"{type(unhook_err).__name__}: {unhook_err}"
                            )
                    content = retry_response.data.content if retry_response else ""
                except Exception as retry_err:
                    logger.error(
                        "[Orchestrator] Recovery after missing session failed: "
                        f"{type(retry_err).__name__}: {retry_err}"
                    )
                    content = "系統會話已失效，已嘗試自動恢復但失敗，請稍後再試。"
            else:
                logger.error(f"[Orchestrator] Unexpected error: {e}")
                content = "系統發生未預期的錯誤，請稍後再試。"
        finally:
            try:
                primary_unsubscribe()
            except Exception as unhook_err:
                logger.warning(
                    f"[TurnEvent][{event.event_id}][primary] unsubscribe_failed "
                    f"{type(unhook_err).__name__}: {unhook_err}"
                )

        wrapper.turn_count += 1

        # 5. Post-process: persist summary
        if content:
            content = await self._calibrate_high_risk_response(content, wrapper, event)

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
