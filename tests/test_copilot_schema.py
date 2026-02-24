import asyncio
from dotenv import load_dotenv
import os

load_dotenv()

async def test_api():
    from copilot import CopilotClient, MessageOptions
    from copilot.types import Tool
    
    token = os.getenv("COPILOT_GITHUB_TOKEN")
         
    client = CopilotClient({"github_token": token, "env": os.environ.copy()})
    
    # 建立一個會回傳很長字串的假 inspect_tool
    long_code = "print('hello')\n" * 500  # 約 7.5KB 的程式碼
    
    mock_tool = Tool(
        name="inspect_tool",
        description="Inspect a tool.",
        parameters={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string"}
            }
        },
        handler=lambda x: {"resultType": "success", "textResultForLlm": str({"status": "success", "code": long_code})}
    )
    
    session = await client.create_session({"tools": [mock_tool]})
    
    def on_event(event):
        print(f"Event: {event.type}")
        if str(event.type) == "session.error":
             print(f"Error details: {event.data.message}")
    
    session.on(on_event)
    
    print("Sending message to trigger inspect_tool...")
    await session.send(MessageOptions(prompt="Please call inspect_tool for tool_name 'foo' and do something with the result."))
    
    await asyncio.sleep(15)
    print("Done")

if __name__ == "__main__":
    asyncio.run(test_api())
