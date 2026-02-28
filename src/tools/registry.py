import copy
import importlib
import importlib.util
import sys
import os
import asyncio
import logging
from typing import Any, Callable, Awaitable, Dict, List, Optional
from pathlib import Path
from copilot.types import Tool, ToolInvocation, ToolResult
from src.core.interfaces import RouteConfig  # deferred import safe: interfaces does not import registry
from src.tools.base import BaseTool

logger = logging.getLogger(__name__)

class ToolRegistry:
    """Registry to manage and retrieve tools with dynamic loading capabilities.

    Supports two tool formats:
    - Legacy ``BaseTool`` subclasses (core/meta tools, dynamic tools, send_telegram_buttons)
    - Native SDK ``Tool`` objects created via ``@define_tool`` (Phase 3a atomic tools)

    Modules using ``@define_tool`` should export:
        EXPORTED_TOOLS: list[Tool]   – list of @define_tool decorated functions
        TOOL_CATEGORY: str           – category name applied to all tools in the module
    """
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}              # Legacy BaseTool instances
        self._native_tools: Dict[str, Tool] = {}           # SDK Tool objects from @define_tool
        self._tool_categories: Dict[str, str] = {}         # tool_name -> category for native tools
        self._lock = asyncio.Lock()  # 🛡️ Prevent race conditions during refresh
        self._broken_modules: set = set()  # 本次啟動期間已知無法載入的模組，下次 refresh 跳過
        self._base_dir = Path(__file__).parent
        self._project_root = self._base_dir.parent.parent
        self.static_path = self._base_dir / "static"
        
        # Phase 1: 原子工具已搬遷至 my-tools/atomic/
        self.atomic_path = self._project_root / "my-tools" / "atomic"
        
        # 移至 storage/dynamic_tools 確保 Docker 容器重啟也能持久化
        self.dynamic_path = self._project_root / "storage" / "dynamic_tools"
        self.dynamic_path.mkdir(parents=True, exist_ok=True)

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        print(f"Tool registered: {tool.name}")

    def get_tool(self, name: str):
        """Return a tool by name (BaseTool or native SDK Tool)."""
        return self._tools.get(name) or self._native_tools.get(name)

    def get_all_schemas(self) -> List[dict]:
        """Return JSON schemas for ALL registered tools (both legacy and native)."""
        schemas = [tool.to_schema() for tool in self._tools.values()]
        for tool_name, tool_obj in self._native_tools.items():
            schemas.append({
                "name": tool_name,
                "category": self._tool_categories.get(tool_name, "general"),
                "description": getattr(tool_obj, "description", ""),
                "parameters": getattr(tool_obj, "parameters", {}),
            })
        return schemas

    def list_tools(self) -> List[str]:
        return list(self._tools.keys()) + list(self._native_tools.keys())

    def get_all_tool_metadata(self) -> List[dict]:
        """Return lightweight metadata for all tools (for catalog building)."""
        metadata = []
        for t in self._tools.values():
            metadata.append({
                "name": t.name,
                "category": getattr(t, "category", "general"),
                "description": t.description,
            })
        for tool_name, tool_obj in self._native_tools.items():
            metadata.append({
                "name": tool_name,
                "category": self._tool_categories.get(tool_name, "general"),
                "description": getattr(tool_obj, "description", ""),
            })
        return metadata

    def to_sdk_tools(
        self,
        route_config: RouteConfig,
        status_callback: Optional[Callable[..., Awaitable[Any]]] = None,
        caller_session_id: Optional[str] = None,
    ) -> list:
        """Convert filtered BaseTool instances to SDK Tool objects.
        Replaces the inline get_filtered_sdk_tools() closure in Orchestrator."""
        active_categories = set(route_config.role.allowed_categories) if route_config.role else set()
        filtered_tools = list(self._tools.values())

        if active_categories:
            filtered_tools = [t for t in filtered_tools if getattr(t, 'category', 'general') in active_categories]

        if route_config.role and route_config.role.allowed_tools:
            allowed_names = set(route_config.role.allowed_tools)
            filtered_tools = [t for t in filtered_tools if t.name in allowed_names]
        else:
            allowed_names = None

        sdk_tools = []
        for tool in filtered_tools:
            def make_handler(t_instance):
                async def handler(invocation: ToolInvocation) -> ToolResult:
                    try:
                        args = invocation.get("arguments", {}) or {}
                        if status_callback:
                            args["status_callback"] = status_callback
                        if caller_session_id:
                            args["caller_session_id"] = caller_session_id
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

            sdk_tools.append(Tool(
                name=tool.name,
                description=tool.description,
                parameters=safe_params,
                handler=make_handler(tool)
            ))

        # Phase 3a: Include native SDK tools (@define_tool) with category filtering
        for tool_name, tool_obj in self._native_tools.items():
            cat = self._tool_categories.get(tool_name, "general")
            if active_categories and cat not in active_categories:
                continue
            if allowed_names and tool_name not in allowed_names:
                continue
            sdk_tools.append(tool_obj)

        return sdk_tools

    def _validate_tool_schema(self, tool) -> str:
        """
        Validates the tool's JSON Schema for common mistakes that cause Copilot API 400 errors.
        Returns an error message string if invalid, or empty string if OK.
        """
        try:
            schema = tool.parameters
            if not isinstance(schema, dict):
                return "parameters must be a dict"
            
            def check_schema(node, path=""):
                if not isinstance(node, dict):
                    return ""
                node_type = node.get("type")
                if node_type == "array" and "items" not in node:
                    return f"array at '{path}' is missing 'items'"
                    
                if node_type == "object" and "properties" not in node:
                    return f"object at '{path}' is missing 'properties'"
                
                # Recurse into properties for object type
                props = node.get("properties", {})
                for k, v in props.items():
                    err = check_schema(v, f"{path}.{k}" if path else k)
                    if err:
                        return err
                
                # Recurse into items for array type
                items = node.get("items")
                if isinstance(items, dict):
                    err = check_schema(items, f"{path}[]")
                    if err:
                        return err
                
                return ""
            
            return check_schema(schema)
        except Exception as e:
            return f"schema validation error: {e}"

    # Define core tools that are registered via DI or specific static logic
    CORE_TOOL_NAMES = {
        "create_tool", "delegate_to_mechanic", "reload_tools",
        "task_status", "cancel_task"
    }

    def _load_from_directory(self, dir_path: Path, prefix: str):
        """Common scanning logic with namespace isolation via prefix."""
        if not dir_path.exists():
            print(f"Directory not found: {dir_path}")
            return

        print(f"Scanning tools in {dir_path} with prefix '{prefix}'...")
        
        # Force re-import to handle filesystem changes
        importlib.invalidate_caches()

        # 使用 rglob 支援巢狀的分類(Category)資料夾掃描
        for f in dir_path.rglob("*.py"):
            if f.name.startswith("__"):
                continue
            
            # 🚫 跳過本次啟動已知無法載入的模組
            if str(f) in self._broken_modules:
                logger.warning(f"Skipping known-broken module: {f.name}")
                continue
            
            # Namespace isolation: dynamic_tool_xxx
            # 如果檔案已經以 prefix 開頭了，就不要再疊加
            if f.stem.startswith(prefix):
                module_name = f.stem
            else:
                module_name = f"{prefix}{f.stem}"
            
            try:
                # Hot Reload: Clear old cache
                if module_name in sys.modules:
                    del sys.modules[module_name]
                
                spec = importlib.util.spec_from_file_location(module_name, str(f))
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    
                    # --- Phase 3a: Check for @define_tool exports first ---
                    exported_tools = getattr(module, 'EXPORTED_TOOLS', None)
                    if exported_tools:
                        category = getattr(module, 'TOOL_CATEGORY', 'general')
                        native_count = 0
                        for tool_obj in exported_tools:
                            tool_name = getattr(tool_obj, 'name', None)
                            if not tool_name:
                                continue
                            if tool_name in self.CORE_TOOL_NAMES:
                                print(f"Tool '{tool_name}' is a core tool, skipping auto-load from {f.name}")
                                continue
                            self._native_tools[tool_name] = tool_obj
                            self._tool_categories[tool_name] = category
                            native_count += 1
                            print(f"Native SDK tool registered: {tool_name} (category={category})")
                        if native_count > 0:
                            print(f"Loaded {native_count} native SDK tools from {f.name}")
                        continue  # Skip BaseTool scanning for this module

                    # --- Legacy: Scan for BaseTool subclasses ---
                    loaded_count = 0
                    for name, obj in vars(module).items():
                        if isinstance(obj, type) and issubclass(obj, BaseTool) and obj is not BaseTool:
                            try:
                                # We need to check if an instance already exists to avoid overwriting DI-injected tools
                                temp_tool = obj.__new__(obj)
                                tool_name = getattr(temp_tool, "name", None)
                                
                                if tool_name and tool_name in self.CORE_TOOL_NAMES:
                                    # 如果是核心工具（由 DI 注入或特定的靜態邏輯處理）則跳過自動載入
                                    print(f"Tool '{tool_name}' is a core tool, skipping auto-load from {f.name}")
                                    continue
                                
                                if tool_name and tool_name in self._tools:
                                    print(f"Tool '{tool_name}' already exists, overwriting with new version from {f.name}")

                                tool_instance = obj()
                                
                                # 🛡️ Schema Validation: Reject tools with invalid JSON schemas before they cause API 400 errors.
                                schema_error = self._validate_tool_schema(tool_instance)
                                if schema_error:
                                    print(f"⚠️ Schema validation failed for '{tool_instance.name}' from {f.name}: {schema_error}")
                                    print(f"   This tool will NOT be registered to prevent API 400 errors.")
                                    continue
                                    
                                self.register(tool_instance)
                                loaded_count += 1
                            except Exception as e:
                                import traceback
                                print(f"Error instantiating tool {name} from {f.name}: {e}")
                                traceback.print_exc()
                    
                    if loaded_count > 0:
                        print(f"Loaded {loaded_count} tools from {f.name}")
                        
            except Exception as e:
                import traceback
                # � 記録到記憑體黑名單，避免下次 refresh 重試。不再自動 rename 檔案，避免誤傷原始碼。
                logger.error(f"Failed to load module {module_name} from {f}: {e}")
                self._broken_modules.add(str(f))
                traceback.print_exc()

    def load_static_tools(self):
        """Load built-in tools (meta-skills + atomic tools from my-tools/)."""
        # 1. 載入 meta-skills (create_tool, reload_tools, task_control, delegate_mechanic...)
        self._load_from_directory(self.static_path, "static_tool_")
        # 2. Phase 1: 載入原子工具 (已搬遷至 my-tools/atomic/)
        self._load_from_directory(self.atomic_path, "static_tool_")

    def load_dynamic_tools(self):
        """Load AI-generated tools."""
        self._load_dynamic_from_directory(self.dynamic_path, "dynamic_tool_")

    def _load_dynamic_from_directory(self, dir_path: Path, prefix: str):
        """Scan for dynamic tools via their .json definition files to avoid memory leaks."""
        if not dir_path.exists():
            return
            
        print(f"Scanning dynamic tools in {dir_path} with prefix '{prefix}'...")
        import json
        from src.tools.dynamic import SubprocessDynamicTool
        
        loaded_count = 0
        for schema_file in dir_path.rglob("*.json"):
            if schema_file.name == "skills_index.json":
                continue
                
            script_file = schema_file.with_suffix(".py")
            if not script_file.exists():
                print(f"Warning: Schema {schema_file.name} found but script {script_file.name} is missing.")
                continue
                
            try:
                with open(schema_file, 'r', encoding='utf-8') as f:
                    schema_data = json.load(f)
                    
                tool_name = schema_data.get("name")
                if not tool_name:
                    continue
                    
                if tool_name in self.CORE_TOOL_NAMES:
                    continue
                    
                tool_instance = SubprocessDynamicTool(
                    name=tool_name,
                    category=schema_data.get("category", "general"),
                    description=schema_data.get("description", ""),
                    parameters=schema_data.get("parameters", {"type": "object", "properties": {}}),
                    script_path=script_file
                )
                
                schema_error = self._validate_tool_schema(tool_instance)
                if schema_error:
                    print(f"⚠️ Schema validation failed from {schema_file.name}: {schema_error}")
                    continue
                    
                self.register(tool_instance)
                loaded_count += 1
            except Exception as e:
                import traceback
                print(f"Failed to load dynamic tool from {schema_file}: {e}")
                traceback.print_exc()
                
        if loaded_count > 0:
            print(f"Loaded {loaded_count} dynamic tools from {dir_path}")

    async def refresh(self) -> dict:
        """Async refresh with lock protection. Also updates the skills index JSON."""
        async with self._lock:
            print("Refreshing tools...")
            # 1. Clear current tools, but preserve DI core tools
            preserved_tools = {name: self._tools[name] for name in self.CORE_TOOL_NAMES if name in self._tools}
            self._tools.clear()
            self._native_tools.clear()
            self._tool_categories.clear()
            self._tools.update(preserved_tools)
            # 2. Reload
            self.load_static_tools()
            self.load_dynamic_tools()
            
            # 3. 匯出技能目錄 (JSON Index) 供快速檢索
            try:
                index_data = self.get_all_schemas()
                index_file = self.dynamic_path / "skills_index.json"
                import json
                with open(index_file, "w", encoding="utf-8") as f:
                    json.dump(index_data, f, ensure_ascii=False, indent=2)
                print(f"Skills index exported to {index_file}")
            except Exception as e:
                print(f"Failed to export skills index: {e}")

            total_count = len(self._tools) + len(self._native_tools)
            print(f"Refresh complete. Total tools: {total_count} (legacy={len(self._tools)}, native={len(self._native_tools)})")
            return {
                "status": "ok", 
                "tool_count": total_count, 
                "tools": self.list_tools()
            }
