import importlib
import importlib.util
import sys
import os
import asyncio
import logging
from typing import Dict, List
from pathlib import Path
from .base import BaseTool

logger = logging.getLogger(__name__)

class ToolRegistry:
    """Registry to manage and retrieve tools with dynamic loading capabilities."""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._lock = asyncio.Lock()  # 🛡️ Prevent race conditions during refresh
        self._base_dir = Path(__file__).parent
        self.static_path = self._base_dir / "static"
        self.dynamic_path = self._base_dir / "dynamic"

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        print(f"Tool registered: {tool.name}")

    def get_tool(self, name: str) -> BaseTool:
        return self._tools.get(name)

    def get_all_schemas(self) -> List[dict]:
        return [tool.to_schema() for tool in self._tools.values()]

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def _load_from_directory(self, dir_path: Path, prefix: str):
        """Common scanning logic with namespace isolation via prefix."""
        if not dir_path.exists():
            print(f"Directory not found: {dir_path}")
            return

        print(f"Scanning tools in {dir_path} with prefix '{prefix}'...")
        
        # Force re-import to handle filesystem changes
        importlib.invalidate_caches()

        for f in dir_path.glob("*.py"):
            if f.name.startswith("__"):
                continue
            
            # Namespace isolation: dynamic_tool_xxx
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
                                tool_instance = obj()
                                # Optional: Verify tool name matches expected pattern?
                                self.register(tool_instance)
                                loaded_count += 1
                            except Exception as e:
                                print(f"Error instantiating tool {name} from {f.name}: {e}")
                    
                    if loaded_count > 0:
                        print(f"Loaded {loaded_count} tools from {f.name}")
                        
            except Exception as e:
                # 🛡️ Failure Rollback: Rename broken files
                print(f"Failed to load module {module_name}: {e}")
                try:
                    broken_path = f.with_suffix(".py.broken")
                    f.rename(broken_path)
                    print(f"Renamed broken file to: {broken_path.name}")
                except Exception as rename_error:
                    print(f"CRITICAL: Failed to rename broken file {f.name}: {rename_error}")

    def load_static_tools(self):
        """Load built-in tools."""
        self._load_from_directory(self.static_path, "static_tool_")

    def load_dynamic_tools(self):
        """Load AI-generated tools."""
        self._load_from_directory(self.dynamic_path, "dynamic_tool_")

    async def refresh(self) -> dict:
        """Async refresh with lock protection."""
        async with self._lock:
            print("Refreshing tools...")
            # 1. Clear current tools
            self._tools.clear()
            
            # 2. Reload
            self.load_static_tools()
            self.load_dynamic_tools()
            
            print(f"Refresh complete. Total tools: {len(self._tools)}")
            return {
                "status": "ok", 
                "tool_count": len(self._tools), 
                "tools": self.list_tools()
            }
