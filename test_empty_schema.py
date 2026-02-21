import asyncio
from dotenv import load_dotenv
import os

load_dotenv()

async def test_api():
    from copilot import CopilotClient, MessageOptions
    from copilot.types import Tool
    
    token = os.getenv("COPILOT_GITHUB_TOKEN")
         
    client = CopilotClient({"github_token": token, "env": os.environ.copy()})
    
    # 測試空的 schema
    empty_schema = {}
    
    mock_tool = Tool(
        name="reload_tools",
        description="Reload all tools.",
        parameters=empty_schema,
        handler=lambda x: {"resultType": "success", "textResultForLlm": "ok"}
    )
    
    session = await client.create_session({"tools": [mock_tool]})
    
    def on_event(event):
        print(f"Event: {event.type}")
        if str(event.type) == "session.error":
             print(f"Error details: {event.data.message}")
    
    session.on(on_event)
    
    print("Sending message...")
    try:
        await session.send(MessageOptions(prompt="Please call reload_tools."))
    except Exception as e:
        print(f"Exception: {e}")
        
    await asyncio.sleep(5)
    print("Done")

if __name__ == "__main__":
    asyncio.run(test_api())
