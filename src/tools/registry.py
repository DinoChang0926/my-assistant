import importlib
import importlib.util
import sys
import os
import asyncio
import logging
from typing import Dict, List
from pathlib import Path
from src.tools.base import BaseTool

logger = logging.getLogger(__name__)

class ToolRegistry:
    """Registry to manage and retrieve tools with dynamic loading capabilities."""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._lock = asyncio.Lock()  # 🛡️ Prevent race conditions during refresh
        self._base_dir = Path(__file__).parent
        self.static_path = self._base_dir / "static"
        
        # 移至 storage/dynamic_tools 確保 Docker 容器重啟也能持久化
        self.dynamic_path = self._base_dir.parent.parent / "storage" / "dynamic_tools"
        self.dynamic_path.mkdir(parents=True, exist_ok=True)

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        print(f"Tool registered: {tool.name}")

    def get_tool(self, name: str) -> BaseTool:
        return self._tools.get(name)

    def get_all_schemas(self) -> List[dict]:
        return [tool.to_schema() for tool in self._tools.values()]

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

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
                    
                    # Scan for BaseTool subclasses
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
                # 🛡️ Failure Rollback: Rename broken files
                print(f"Failed to load module {module_name} from {f}: {e}")
                traceback.print_exc()
                try:
                    broken_path = f.with_suffix(".py.broken")
                    f.rename(broken_path)
                    print(f"Renamed broken file to: {broken_path.name}")
                except Exception as rename_error:
                    print(f"CRITICAL: Failed to rename broken file {f.name}: {rename_error}")

    def load_static_tools(self):
        """Load built-in tools."""
        # Using rglob in _load_from_directory already scans subdirectories (like atomic)
        self._load_from_directory(self.static_path, "static_tool_")

    def load_dynamic_tools(self):
        """Load AI-generated tools."""
        self._load_from_directory(self.dynamic_path, "dynamic_tool_")

    async def refresh(self) -> dict:
        """Async refresh with lock protection. Also updates the skills index JSON."""
        async with self._lock:
            print("Refreshing tools...")
            # 1. Clear current tools, but preserve DI core tools
            preserved_tools = {name: self._tools[name] for name in self.CORE_TOOL_NAMES if name in self._tools}
            self._tools.clear()
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

            print(f"Refresh complete. Total tools: {len(self._tools)}")
            return {
                "status": "ok", 
                "tool_count": len(self._tools), 
                "tools": self.list_tools()
            }
