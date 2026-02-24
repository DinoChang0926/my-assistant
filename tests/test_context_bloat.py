import asyncio
from dotenv import load_dotenv
import os

load_dotenv()

async def test_context_bloat():
    from copilot import CopilotClient, MessageOptions
    from copilot.types import Tool
    
    token = os.getenv("COPILOT_GITHUB_TOKEN")
    client = CopilotClient({"github_token": token, "env": os.environ.copy()})
    
    # 建立一個會回傳超巨大字串 (10000 字元) 的技能，模擬被截斷後的長度
    def giant_handler(x):
        return {"resultType": "success", "textResultForLlm": "A" * 10000}
        
    giant_tool = Tool(
        name="giant_fetch",
        description="Return a giant 10000-char string.",
        parameters={},
        handler=giant_handler
    )
    
    session = await client.create_session({"tools": [giant_tool]})
    
    # 添加事件監聽來捕捉報錯
    def on_event(event):
        e_type = str(event.type)
        if e_type == "session.error":
             print(f"[ERROR Caught] {event.data.message}")
        elif e_type == "tool.execution_start":
             print(f"Tool {event.data.tool_name} started.")
             
    session.on(on_event)
    
    print("----- Round 1 -----")
    try:
        await session.send(MessageOptions(prompt="Call giant_fetch immediately."))
    except Exception as e:
        print(e)
        
    await asyncio.sleep(8)
    
    print("\n----- Round 2 -----")
    try:
        await session.send(MessageOptions(prompt="Call it again."))
    except Exception as e:
        print(e)
        
    await asyncio.sleep(8)
    
    print("\n----- Round 3 -----")
    try:
        await session.send(MessageOptions(prompt="And once more, call giant_fetch."))
    except Exception as e:
        print(e)
        
    # 等待
    await asyncio.sleep(15)
    print("\nTest completed.")

if __name__ == "__main__":
    asyncio.run(test_context_bloat())
