import inspect
import copilot.types
from copilot import CopilotClient

try:
    print("SessionConfig structure:")
    import json
    # Try to print all annotations
    if hasattr(copilot.types.SessionConfig, "__annotations__"):
        print("Annotations:", list(copilot.types.SessionConfig.__annotations__.keys()))
    
    # Try to inspect the __init__ of SessionConfig if possible, or just dir()
    print("Dir:", [d for d in dir(copilot.types.SessionConfig) if not d.startswith("_")])
except Exception as e:
    print(f"Error inspecting SessionConfig: {e}")

