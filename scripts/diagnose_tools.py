import sys
import os
import asyncio
import traceback

# Add src to path
sys.path.append(os.getcwd())

from src.tools.registry import ToolRegistry

async def main():
    with open("diagnose_output.txt", "w", encoding="utf-8") as log_file:
        sys.stdout = log_file
        sys.stderr = log_file
        
        print("Diagnosing tools...")
        try:
            registry = ToolRegistry()
            
            # Manual registration for DI tools (matching main.py)
            from src.tools.static.create_tool import CreateToolTool
            from src.tools.static.reload_tools import ReloadToolsTool
            
            registry.register(CreateToolTool(registry=registry))
            registry.register(ReloadToolsTool(registry=registry))
            
            # Manually trigger load and catch anything registry doesn't catch
            print("Loading static tools...")
            registry.load_static_tools()
            print("Loading dynamic tools...")
            registry.load_dynamic_tools()
            
            print(f"Total tools loaded: {len(registry._tools)}")
            for name, tool in registry._tools.items():
                print(f"Tool: {name} (loaded from {tool.__class__.__module__})")
        except Exception:
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
