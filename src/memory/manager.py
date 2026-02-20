import asyncio
import os
from pathlib import Path
from typing import Dict, Optional, Any
from copilot import CopilotClient

# Import settings but handle potential import errors gracefully if needed
try:
    from src.config import settings
except ImportError:
    import sys
    sys.modules["src.config"] = object()
    class MockSettings:
        SESSION_STORAGE_PATH = "storage"
        COPILOT_MODEL = "claude-3.5-sonnet"
        SESSION_MAX_TURNS = 30
    settings = MockSettings()

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
        self.storage_path = Path(settings.SESSION_STORAGE_PATH).resolve()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, SessionWrapper] = {}
        print(f"SessionManager initialized with storage: {self.storage_path}")

    async def get_or_create(self, session_id: str, route_config: RouteConfig, tools: Optional[list] = None) -> SessionWrapper:
        # 1. Try to Resume or Sync existing
        config_dir = str(self.storage_path)
        
        # Prepare config with tools and system prompt
        resume_config = {
            "config_dir": config_dir
        }
        if route_config.system_prompt is not None:
             resume_config["system_message"] = route_config.system_prompt
             print(f"[Session] Resume with custom System Prompt (Role: {route_config.role.role_id if route_config.role else 'unknown'})")
        else:
             print(f"[Session] Resume with NATIVE Behavior (Role: {route_config.role.role_id if route_config.role else 'unknown'})")

        if route_config.model_name:
            resume_config["model"] = route_config.model_name
        if tools:
            resume_config["tools"] = tools

        try:
            print(f"Syncing/Resuming session {session_id}...")
            sdk_session = await self.client.resume_session(
                session_id=session_id,
                config=resume_config
            )
            print(f"Successfully synced/resumed session: {session_id}")
            wrapper = SessionWrapper(session_id, sdk_session)
            self._sessions[session_id] = wrapper
            return wrapper
        except Exception as e:
            if session_id in self._sessions:
                 print(f"Resume context failed, falling back to cached session: {e}")
                 return self._sessions[session_id]
            print(f"Resume failed (expected for new sessions): {e}")

        # 2. Create New
        print(f"Creating new session {session_id}...")
        try:
            session_config = {}
            if route_config.system_prompt is not None:
                session_config["system_message"] = route_config.system_prompt
            
            if route_config.model_name:
                session_config["model"] = route_config.model_name
            
            if tools:
                session_config["tools"] = tools

            sdk_session = await self.client.create_session(session_config)
            
            wrapper = SessionWrapper(session_id, sdk_session)
            self._sessions[session_id] = wrapper
            return wrapper
        except Exception as e:
            print(f"Failed to create session: {e}")
            raise

    async def cleanup_all(self):
        # We don't want to destroy sessions on exit if we want persistence!
        # Just clear memory references.
        # If we call destroy(), the SDK might delete the persistent state.
        self._sessions.clear()
        print("SessionManager cleanup complete (sessions preserved on disk).")
