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

    def _get_mapping_file(self) -> Path:
        return self.storage_path / "session_mapping.json"

    def _load_mapping(self) -> Dict[str, str]:
        mapping_file = self._get_mapping_file()
        if mapping_file.exists():
            try:
                import json
                with open(mapping_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_mapping(self, mapping: dict):
        import json
        try:
            with open(self._get_mapping_file(), "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=2)
        except Exception as e:
            print(f"Error saving session mapping: {e}")

    async def get_or_create(self, session_id: str, route_config: RouteConfig, tools: Optional[list] = None) -> SessionWrapper:
        # Load persistent mapping to find the actual SDK UUID
        mapping = self._load_mapping()
        
        # 為了支援 Sub-agent，同一個聊天室 (session_id) 會有不同的 Role
        # 我們必須將不同的 Role 對應到不同的 SDK Session，避免 API Tools 衝突
        role_id = route_config.role.role_id if route_config.role else "default"
        namespaced_session_id = f"{session_id}_{role_id}"
        
        sdk_session_id = mapping.get(namespaced_session_id)

        # 1. Try to Resume or Sync existing
        config_dir = str(self.storage_path)
        
        # Prepare config with tools and system prompt
        resume_config = {
            "config_dir": config_dir
        }
        if route_config.system_prompt is not None:
             # SDK types specify SystemMessageConfig is a dict with 'mode' and 'content'
             resume_config["system_message"] = {"mode": "replace", "content": route_config.system_prompt}
             print(f"[Session] Resume with custom System Prompt (Role: {route_config.role.role_id if route_config.role else 'unknown'})")
        else:
             print(f"[Session] Resume with NATIVE Behavior (Role: {route_config.role.role_id if route_config.role else 'unknown'})")

        if route_config.model_name:
            resume_config["model"] = route_config.model_name
            
        # 嚴厲封鎖 SDK 原生工具，避免子代理人亂寫檔案或執行高危險指令
        banned_native_tools = ["create", "replace", "view", "run_command", "run_terminal_command"]
        resume_config["excluded_tools"] = banned_native_tools

        if tools:
            resume_config["tools"] = tools

        if sdk_session_id:
            try:
                print(f"Syncing/Resuming session UUID {sdk_session_id} for local alias {session_id}...")
                sdk_session = await self.client.resume_session(
                    session_id=sdk_session_id,
                    config=resume_config
                )
                print(f"Successfully synced/resumed session UUID: {sdk_session_id}")
                wrapper = SessionWrapper(session_id, sdk_session)
                self._sessions[session_id] = wrapper
                return wrapper
            except Exception as e:
                err_msg = str(e)
                if "Session not found" in err_msg:
                    print(f"Session UUID {sdk_session_id} not found on server, will create a new one.")
                elif namespaced_session_id in self._sessions:
                     print(f"Resume context failed, falling back to cached session: {e}")
                     return self._sessions[namespaced_session_id]
                else:
                     print(f"Resume failed: {e}")
        else:
            print(f"No existing mapping for {session_id}, creating new.")

        # 2. Create New
        print(f"Creating new session {session_id}...")
        try:
            session_config = {}
            if route_config.system_prompt is not None:
                # SDK types specify SystemMessageConfig is a dict with 'mode' and 'content'
                session_config["system_message"] = {"mode": "replace", "content": route_config.system_prompt}
            
            if route_config.model_name:
                session_config["model"] = route_config.model_name
                
            # 嚴厲封鎖 SDK 原生工具，避免子代理人亂寫檔案或執行高危險指令
            banned_native_tools = ["create", "replace", "view", "run_command", "run_terminal_command"]
            session_config["excluded_tools"] = banned_native_tools
            
            if tools:
                session_config["tools"] = tools

            sdk_session = await self.client.create_session(session_config)
            
            # Save the new mapping
            mapping[namespaced_session_id] = sdk_session.session_id
            self._save_mapping(mapping)
            print(f"Mapped {namespaced_session_id} -> UUID {sdk_session.session_id}")

            wrapper = SessionWrapper(session_id, sdk_session)
            self._sessions[namespaced_session_id] = wrapper
            return wrapper
        except Exception as e:
            print(f"Failed to create session: {e}")
            raise

    def invalidate_session(self, session_id: str, route_config=None):
        """
        Invalidates a broken session so the next call will create a fresh one.
        Called when an OSError / BrokenPipeError is detected on the SDK pipe.
        """
        role_id = route_config.role.role_id if (route_config and route_config.role) else "default"
        namespaced = f"{session_id}_{role_id}"
        
        # 1. Remove from in-memory cache
        self._sessions.pop(namespaced, None)
        self._sessions.pop(session_id, None)
        
        # 2. Remove from persistent mapping (force new SDK session on next call)
        mapping = self._load_mapping()
        if namespaced in mapping:
            del mapping[namespaced]
            self._save_mapping(mapping)
            
        print(f"[SessionManager] Session invalidated for {namespaced} — will create fresh session on retry.")

    def soft_invalidate(self, session_id: str, route_config=None):
        """
        Soft invalidation: only clears in-memory cache.
        The UUID in session_mapping.json is preserved so the session can be
        resumed on the next call. Use this for temporary rebuilds (e.g., pipe errors)
        that should NOT destroy the user's conversation history.
        """
        role_id = route_config.role.role_id if (route_config and route_config.role) else "default"
        namespaced = f"{session_id}_{role_id}"

        self._sessions.pop(namespaced, None)
        self._sessions.pop(session_id, None)

        print(f"[SessionManager] Session soft-invalidated for {namespaced} — UUID preserved on disk, will resume on next call.")

    async def cleanup_all(self):
        # We don't want to destroy sessions on exit if we want persistence!
        # Just clear memory references.
        # If we call destroy(), the SDK might delete the persistent state.
        self._sessions.clear()
        print("SessionManager cleanup complete (sessions preserved on disk.")
