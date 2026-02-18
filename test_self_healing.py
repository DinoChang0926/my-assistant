import asyncio
from src.brain.orchestrator import TaskOrchestrator
from src.memory.manager import SessionManager
from src.tools.registry import ToolRegistry
from src.core.events import AgentEvent
from src.core.interfaces import RouteConfig
from src.config import settings

async def test_self_healing():
    print("--- Testing Self-Healing Logic ---")
    
    # 1. Setup components
    registry = ToolRegistry()
    registry.load_static_tools()
    
    # We don't need a real SDK session for the internal logic test if we mock things,
    # but let's just test the _process_tool_execution logic directly.
    
    class MockSession:
        def __init__(self):
            self.session_id = "test_session"
            self.submitted = []
        async def submit_tool_outputs(self, outputs):
            self.submitted.extend(outputs)
            print(f"Submitted to LLM: {outputs[0]['output'][:200]}...")

    orch = TaskOrchestrator(None, registry)
    session = MockSession()
    
    # Mock event object from SDK
    class MockEvent:
        def __init__(self, name, call_id, args):
            self.data = type('obj', (object,), {
                'tool_name': name,
                'tool_call_id': call_id,
                'arguments': args
            })

    # Test Case 1: Missing Tool
    print("\nCase 1: Missing Tool 'not_exist_tool'")
    event1 = MockEvent("not_exist_tool", "call_1", {})
    await orch._process_tool_execution(session, event1, [])
    
    if "【能力缺失/執行錯誤偵測】" in session.submitted[-1]['output']:
        print("✅ SUCCESS: Skill acquisition prompt appended for missing tool.")
    else:
        print("❌ FAILURE: Prompt not found.")

    # Test Case 2: Tool Execution Error
    print("\nCase 2: Tool Execution Error")
    # We'll use 'hello_world' but pass bad args or rely on its internal failure if we had one.
    # Actually let's just use fibonacci which we created in dynamic if it exists
    registry.load_dynamic_tools()
    event2 = MockEvent("fibonacci", "call_2", {"n": -1}) # Should return error status but not raise exception
    await orch._process_tool_execution(session, event2, [])
    
    # Fibonacci returns {"status": "error"} but doesn't raise exception in execute.
    # Wait, my orchestrator only appends prompt on 'Exception' or 'Not Found'.
    # If the tool returns a result with error status, it doesn't currently trigger self-healing.
    # Maybe it should? Let's check my orchestrator logic.
    
    # My orchestrator:
    # if tool: try: result = ... except Exception as e: error_context = ...
    
    # So I need an actual exception.
    class BrokenTool:
        def __init__(self): self.name = "broken"
        async def execute(self, **kwargs): raise ValueError("Boom!")
    
    registry.register(BrokenTool())
    event3 = MockEvent("broken", "call_3", {})
    await orch._process_tool_execution(session, event3, [])
    
    if "【能力缺失/執行錯誤偵測】" in session.submitted[-1]['output']:
        print("✅ SUCCESS: Skill acquisition prompt appended for execution error.")
    else:
        print("❌ FAILURE: Prompt not found.")

if __name__ == "__main__":
    asyncio.run(test_self_healing())
