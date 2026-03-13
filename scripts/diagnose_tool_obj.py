import sys
from pathlib import Path

# Add my-tools to path
BASE_DIR = Path("my-tools")
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

try:
    from atomic.static_tool_web_search import web_search
    print(f"Type of web_search: {type(web_search)}")
    print(f"Attributes: {dir(web_search)}")
    if hasattr(web_search, 'name'):
        print(f"Name: {web_search.name}")
    if hasattr(web_search, 'description'):
        print(f"Description: {web_search.description}")
    if hasattr(web_search, 'parameters'):
        print(f"Parameters: {web_search.parameters}")
    if hasattr(web_search, 'handler'):
        print(f"Handler: {web_search.handler}")
except Exception as e:
    print(f"Error: {e}")
