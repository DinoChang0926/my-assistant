# Fix import order to load env before settings
from dotenv import load_dotenv
import asyncio
import os

# Load env FIRST before importing any config-dependent modules
load_dotenv()

from src.tools.static.create_tool import CreateToolTool
from src.tools.static.inspect_tool import InspectToolTool
from src.tools.static.submit_tool_pr import SubmitToolToRepoTool
from src.tools.registry import ToolRegistry
from src.perception import rest_api
from src.config import settings

async def run_test():
    print("--- Starting Evolution Flow Test ---")
    print(f"DEBUG: Repo Name from Settings: {settings.GITHUB_REPO_NAME}")
    
    # Setup Registry
    registry = ToolRegistry()
    registry.load_static_tools()
    registry.load_dynamic_tools()
    rest_api.set_tool_registry(registry)
    
    # 1. Test CreateToolTool
    creator = CreateToolTool()
    fib_code = """from src.tools.base import BaseTool

class FibonacciTool(BaseTool):
    @property
    def name(self) -> str:
        return "fibonacci"
    
    @property
    def description(self) -> str:
        return "計算費式數列。"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "要計算的項數"}
            },
            "required": ["n"]
        }

    async def execute(self, n: int, **kwargs) -> dict:
        if n < 0: return {"status": "error", "message": "n must be >= 0"}
        a, b = 0, 1
        for _ in range(n):
            a, b = b, a + b
        return {"status": "success", "result": a}
"""
    print("Step 1: Creating Tool 'fibonacci'...")
    res1 = await creator.execute(tool_name="fibonacci", code_content=fib_code)
    print(f"Result 1: {res1.get('status')} - {res1.get('message')}")
    
    if res1.get('status') != "success":
        # Force continue if file exists but registry reload failed (e.g. separate process)
        if "registry refresh failed" in res1.get('message', ''):
             print("Warning: Registry refresh skipped (expected in standalone script), continuing...")
        else:
             return

    # 2. Test InspectToolTool
    inspector = InspectToolTool()
    print("Step 2: Inspecting Tool 'fibonacci'...")
    res2 = await inspector.execute(tool_name="fibonacci")
    print(f"Result 2: {res2.get('status')} - Found at {res2.get('file_path')}")
    
    # 3. Test SubmitToolToRepoTool
    submitter = SubmitToolToRepoTool()
    print("Step 3: Submitting Tool 'fibonacci' (standalone test)...")
    
    # Manually inject settings if pydantic loaded too early
    import os
    if not settings.GITHUB_REPO_NAME:
        settings.GITHUB_REPO_NAME = os.getenv("GITHUB_REPO_NAME")
    if not settings.COPILOT_GITHUB_TOKEN:
        settings.COPILOT_GITHUB_TOKEN = os.getenv("COPILOT_GITHUB_TOKEN")

    res3 = await submitter.execute(tool_name="fibonacci", purpose="Add fibonacci helper for sequence calculations.")
    print(f"Result 3: {res3.get('status')} - {res3.get('message')}")

if __name__ == "__main__":
    asyncio.run(run_test())
