import asyncio
import sys
import os
from typing import Dict, Optional, Any
from copilot import CopilotClient

# Import settings but handle potential import errors gracefully if needed
try:
    from src.config import settings
except ImportError:
    class MockSettings:  # type: ignore
        COPILOT_MODEL = "claude-sonnet-4.5"
        SESSION_MAX_TURNS = 30
    settings = MockSettings()  # type: ignore

from src.core.interfaces import RouteConfig

class SessionWrapper:
    """Simple wrapper to satisfy Orchestrator expectations."""
    def __init__(self, session_id: str, sdk_session: Any):
        self.session_id = session_id
        self.sdk_session = sdk_session
        self.turn_count = 0  # Reset on restart for now, or load from SDK history length
        self.summary = None

class SessionManager:
    """
    Manages Copilot SDK sessions using the SDK's built-in persistence
    via 'config_dir' and 'resume_session'.
    """
    
    def __init__(self, client: CopilotClient):
        self.client = client
        self._sessions: Dict[str, SessionWrapper] = {}
        self._skip_resume: set = set()  # 標記下次應跳過 resume 直接 create 的 session
        print("SessionManager initialized.")

    @staticmethod
    def _looks_like_mcp_error(err: Exception) -> bool:
        err_str = str(err).lower()
        keywords = [
            "127.0.0.1:8001",
            "connection refused",
            "connect call failed",
            "mcp",
            "sse",
            "failed to fetch",
            "ecconnrefused",
        ]
        return any(k in err_str for k in keywords)

    def _build_config(self, route_config: RouteConfig, tools: Optional[list] = None) -> dict:
        """Build session configuration dict from a RouteConfig."""
        config: dict = {"streaming": True}

        if route_config.system_prompt is not None:
            config["system_message"] = {"mode": "replace", "content": route_config.system_prompt}
            print(f"[Session] Using custom System Prompt (Role: {route_config.role.role_id if route_config.role else 'unknown'})")
        else:
            print(f"[Session] Using native behavior (Role: {route_config.role.role_id if route_config.role else 'unknown'})")

        if route_config.model_name:
            config["model"] = route_config.model_name

        # Block dangerous native SDK tools
        config["excluded_tools"] = ["create", "replace", "view", "run_command", "run_terminal_command"]

        if tools:
            config["tools"] = tools

        # Phase 3: Connect to local MCP server
        # We use sys.executable to ensure we use the same environment/venv
        # We set PYTHONPATH to include the project root so 'my_tools' can be found if needed,
        # but here we point directly to server.py.
        config["mcp_servers"] = {
            "my-tools": {
                "type": "http",
                "url": "http://127.0.0.1:8001/sse"
            }
        }

        return config

    async def get_or_create(self, session_id: str, route_config: RouteConfig, tools: Optional[list] = None) -> 'SessionWrapper':
        role_id = route_config.role.role_id if route_config.role else "default"
        sdk_id = f"{session_id}_{role_id}"
        is_supervisor = (role_id == "supervisor")

        # 1. Return cached session if available
        if sdk_id in self._sessions:
            return self._sessions[sdk_id]

        config = self._build_config(route_config, tools)

        async def _resume_or_create(target_config: dict):
            try:
                print(f"[Session] Resuming {sdk_id}...")
                resumed = await self.client.resume_session(session_id=sdk_id, config=target_config)
                print(f"[Session] Resumed {sdk_id}")
                return resumed
            except Exception as resume_err:
                err_str = str(resume_err)
                is_not_found = "Session not found" in err_str or "not found" in err_str.lower()

                if is_supervisor and not is_not_found:
                    print(f"[Session] ⚠️ Supervisor resume failed ({resume_err}). Retrying safe-mode (no tools)...")
                    try:
                        safe_config = self._build_config(route_config, tools=None)
                        safe_config.pop("mcp_servers", None)
                        resumed = await self.client.resume_session(session_id=sdk_id, config=safe_config)
                        print(f"[Session] ✅ Supervisor resumed in SAFE MODE (tools stripped): {sdk_id}")
                        return resumed
                    except Exception as e2:
                        print(f"[Session] 🚨 Supervisor safe-mode resume also failed ({e2}). Refusing to create new session.")
                        raise RuntimeError(
                            f"Supervisor session '{sdk_id}' cannot be resumed and MUST NOT be recreated "
                            f"to preserve conversation history. Original error: {resume_err}, Safe-mode error: {e2}"
                        ) from e2

                print(f"[Session] Resume failed ({resume_err}), creating new session {sdk_id}...")
                create_config = dict(target_config)
                create_config["session_id"] = sdk_id
                created = await self.client.create_session(create_config)
                print(f"[Session] Created {sdk_id}")
                return created

        # 1.5 如果被標記為 force_recreate，跳過 resume 直接 create
        if sdk_id in self._skip_resume:
            self._skip_resume.discard(sdk_id)
            print(f"[Session] ⚠️ Force-recreate flagged for {sdk_id}, skipping resume...")
            config["session_id"] = sdk_id
            sdk_session = await self.client.create_session(config)
            print(f"[Session] Created (force-recreate) {sdk_id}")
            wrapper = SessionWrapper(sdk_id, sdk_session)
            self._sessions[sdk_id] = wrapper
            return wrapper

        # 2. Try MCP-enabled path first; fallback to MCP-disabled when MCP is unavailable.
        try:
            sdk_session = await _resume_or_create(config)
        except RuntimeError:
            raise
        except Exception as e:
            if self._looks_like_mcp_error(e):
                print(f"[Session] ⚠️ MCP unavailable ({e}). Retrying without mcp_servers...")
                no_mcp_config = dict(config)
                no_mcp_config.pop("mcp_servers", None)
                sdk_session = await _resume_or_create(no_mcp_config)
            else:
                raise

        wrapper = SessionWrapper(sdk_id, sdk_session)
        self._sessions[sdk_id] = wrapper
        return wrapper

    def invalidate(self, session_id: str, route_config=None, preserve_history: bool = False, force_recreate: bool = False):
        """
        Clears the in-memory session cache entry.
        If force_recreate=True, the next get_or_create will skip resume and
        directly create a new session (to break resume→hang→invalidate loops).
        """
        role_id = route_config.role.role_id if (route_config and route_config.role) else "default"
        sdk_id = f"{session_id}_{role_id}"
        self._sessions.pop(sdk_id, None)
        if force_recreate:
            self._skip_resume.add(sdk_id)
            print(f"[SessionManager] Session invalidated + force-recreate queued: {sdk_id}")
        else:
            print(f"[SessionManager] Session invalidated: {sdk_id}")

    async def cleanup_all(self):
        """Clear in-memory references. Sessions remain on server for future resumption."""
        self._sessions.clear()
        print("SessionManager cleanup complete (sessions preserved on server).")
