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
from src.core.interfaces import RouteConfig
from src.tools.base import BaseTool

logger = logging.getLogger(__name__)

class ToolRegistry:
    """Registry to manage and retrieve tools.
    
    [Phase 3-C]: This registry is now severely weakened. It ONLY loads
    local meta-skills (like task_status, cancel_task) placed in `src/tools/static/`.
    Atomic tools and dynamic tools have been migrated to the external MCP server.
    """
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._lock = asyncio.Lock()
        self._broken_modules: set = set()
        self._base_dir = Path(__file__).parent
        self._project_root = self._base_dir.parent.parent
        self.static_path = self._base_dir / "static"

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        print(f"Tool registered: {tool.name}")

    def get_tool(self, name: str):
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def to_sdk_tools(
        self,
        route_config: RouteConfig,
        status_callback: Optional[Callable[..., Awaitable[Any]]] = None,
        caller_session_id: Optional[str] = None,
    ) -> list:
        active_categories = set(route_config.role.allowed_categories) if route_config.role else set()
        filtered_tools = list(self._tools.values())

        if active_categories:
            filtered_tools = [t for t in filtered_tools if getattr(t, 'category', 'general') in active_categories]

        if route_config.role and route_config.role.allowed_tools:
            allowed_names = set(route_config.role.allowed_tools)
            filtered_tools = [t for t in filtered_tools if t.name in allowed_names]

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

            safe_params = copy.deepcopy(tool.parameters) if tool.parameters else {"type": "object", "properties": {}}
            if safe_params.get("type") == "object" and "properties" not in safe_params:
                safe_params["properties"] = {}

            sdk_tools.append(Tool(
                name=tool.name,
                description=tool.description,
                parameters=safe_params,
                handler=make_handler(tool)
            ))

        return sdk_tools

    def _validate_tool_schema(self, tool) -> str:
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
                
                props = node.get("properties", {})
                for k, v in props.items():
                    err = check_schema(v, f"{path}.{k}" if path else k)
                    if err:
                        return err
                
                items = node.get("items")
                if isinstance(items, dict):
                    err = check_schema(items, f"{path}[]")
                    if err:
                        return err
                
                return ""
            
            return check_schema(schema)
        except Exception as e:
            return f"schema validation error: {e}"

    CORE_TOOL_NAMES = {
        "task_status", "cancel_task", "send_telegram_buttons"
    }

    def _load_from_directory(self, dir_path: Path, prefix: str):
        if not dir_path.exists():
            return

        print(f"Scanning tools in {dir_path} with prefix '{prefix}'...")
        importlib.invalidate_caches()

        for f in dir_path.rglob("*.py"):
            if f.name.startswith("__"):
                continue
            
            if str(f) in self._broken_modules:
                logger.warning(f"Skipping known-broken module: {f.name}")
                continue
            
            if f.stem.startswith(prefix):
                module_name = f.stem
            else:
                module_name = f"{prefix}{f.stem}"
            
            try:
                if module_name in sys.modules:
                    del sys.modules[module_name]
                
                spec = importlib.util.spec_from_file_location(module_name, str(f))
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    
                    loaded_count = 0
                    for name, obj in vars(module).items():
                        if isinstance(obj, type) and issubclass(obj, BaseTool) and obj is not BaseTool:
                            try:
                                temp_tool = obj.__new__(obj)
                                tool_name = getattr(temp_tool, "name", None)
                                
                                if tool_name and tool_name in self.CORE_TOOL_NAMES:
                                    print(f"Tool '{tool_name}' is a core tool, skipping auto-load from {f.name}")
                                    continue
                                
                                tool_instance = obj()
                                schema_error = self._validate_tool_schema(tool_instance)
                                if schema_error:
                                    print(f"⚠️ Schema validation failed: {schema_error}")
                                    continue
                                    
                                self.register(tool_instance)
                                loaded_count += 1
                            except Exception as e:
                                logger.error(f"Error instantiating tool {name}: {e}")
                    
            except Exception as e:
                logger.error(f"Failed to load module {module_name} from {f}: {e}")
                self._broken_modules.add(str(f))

    def load_static_tools(self):
        """[Phase 3-C] Only load meta-skills from src/tools/static"""
        self._load_from_directory(self.static_path, "static_tool_")

    async def refresh(self) -> dict:
        """Async refresh with lock protection."""
        async with self._lock:
            print("Refreshing meta-tools...")
            preserved_tools = {name: self._tools[name] for name in self.CORE_TOOL_NAMES if name in self._tools}
            self._tools.clear()
            self._tools.update(preserved_tools)
            
            self.load_static_tools()
            
            total_count = len(self._tools)
            print(f"Refresh complete. Total meta-tools: {total_count}")
            return {
                "status": "ok", 
                "tool_count": total_count, 
                "tools": self.list_tools()
            }
