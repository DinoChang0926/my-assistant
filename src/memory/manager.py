import asyncio
import os
from pathlib import Path
from typing import Dict, Optional, Any
from copilot import CopilotClient

# Import settings but handle potential import errors gracefully if needed
try:
    from ..config import settings
except ImportError:
    import sys
    sys.modules["..config"] = object()
    class MockSettings:
        SESSION_STORAGE_PATH = "storage"
        COPILOT_MODEL = "claude-3.5-sonnet"
        SESSION_MAX_TURNS = 30
    settings = MockSettings()

from ..core.interfaces import RouteConfig

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

    async def get_or_create(self, session_id: str, route_config: RouteConfig) -> SessionWrapper:
        # Return existing in-memory session if active
        if session_id in self._sessions:
            return self._sessions[session_id]
            
        config_dir = str(self.storage_path)
        
        # 1. Try to Resume
        try:
            print(f"Attempting to resume session {session_id} from {config_dir}...")
            sdk_session = await self.client.resume_session(
                session_id=session_id,
                config={
                    "config_dir": config_dir
                }
            )
            print(f"Successfully resumed session: {session_id}")
            wrapper = SessionWrapper(session_id, sdk_session)
            # Optional: Populate turn_count from message history
            # msgs = await sdk_session.get_messages()
            # wrapper.turn_count = len(msgs)
            self._sessions[session_id] = wrapper
            return wrapper
        except Exception as e:
            print(f"Resume failed (expected for new sessions): {e}")

        # 2. Create New
        print(f"Creating new session {session_id}...")
        try:
            sdk_session = await self.client.create_session({
                "model": route_config.model_name,
                "session_id": session_id,
                "config_dir": config_dir,
                "system_message": route_config.system_prompt
            })
            
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
