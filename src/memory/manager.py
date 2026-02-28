import asyncio
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
        print("SessionManager initialized.")

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

        return config

    async def get_or_create(self, session_id: str, route_config: RouteConfig, tools: Optional[list] = None) -> 'SessionWrapper':
        role_id = route_config.role.role_id if route_config.role else "default"
        sdk_id = f"{session_id}_{role_id}"

        # 1. Return cached session if available
        if sdk_id in self._sessions:
            return self._sessions[sdk_id]

        config = self._build_config(route_config, tools)

        # 2. Try to resume existing session, fall back to creating a new one
        try:
            print(f"[Session] Resuming {sdk_id}...")
            sdk_session = await self.client.resume_session(session_id=sdk_id, config=config)
            print(f"[Session] Resumed {sdk_id}")
        except Exception as e:
            print(f"[Session] Resume failed ({e}), creating new session {sdk_id}...")
            config["session_id"] = sdk_id
            sdk_session = await self.client.create_session(config)
            print(f"[Session] Created {sdk_id}")

        wrapper = SessionWrapper(sdk_id, sdk_session)
        self._sessions[sdk_id] = wrapper
        return wrapper

    def invalidate(self, session_id: str, route_config=None, preserve_history: bool = False):
        """
        Clears the in-memory session cache entry. On the next request, get_or_create
        will attempt resume_session first (using the sdk_id), falling back to
        create_session if the session is broken or not found.
        preserve_history is kept for API compatibility and has no functional effect.
        """
        role_id = route_config.role.role_id if (route_config and route_config.role) else "default"
        sdk_id = f"{session_id}_{role_id}"
        self._sessions.pop(sdk_id, None)
        print(f"[SessionManager] Session invalidated: {sdk_id}")

    async def cleanup_all(self):
        """Clear in-memory references. Sessions remain on server for future resumption."""
        self._sessions.clear()
        print("SessionManager cleanup complete (sessions preserved on server).")
