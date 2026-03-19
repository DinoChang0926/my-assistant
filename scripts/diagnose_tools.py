import sys
import asyncio
import traceback
from pathlib import Path

# Add project root to path (cwd-independent)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.tools.registry import ToolRegistry

async def main():
    log_path = Path(__file__).resolve().with_name("diagnose_output.txt")
    with open(log_path, "w", encoding="utf-8") as log_file:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
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
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

if __name__ == "__main__":
    asyncio.run(main())
