import asyncio
import os
import sys
from copilot import CopilotClient
from src.core.interfaces import RouteConfig
from src.core.roles import RoleRegistry
from src.memory.manager import SessionManager
from dotenv import load_dotenv

# Load .env
load_dotenv()

async def verify_mcp_integration():
    token = os.environ.get("COPILOT_GITHUB_TOKEN")
    if not token:
        print("Missing COPILOT_GITHUB_TOKEN in .env")
        return

    # Initialize client
    client = CopilotClient({"github_token": token})
    await client.start()

    try:
        # Initialize SessionManager
        manager = SessionManager(client)

        # Create a route config for Supervisor
        route_config = RouteConfig(
            role=RoleRegistry.SUPERVISOR,
            model_name="claude-sonnet-4.5"
        )

        # 這裡會觸發 _build_config 注入 MCP 設定
        print("Creating session with MCP integration...")
        wrapper = await manager.get_or_create("test_mcp_session", route_config)
        
        # Test calling a tool from MCP (web_search)
        # Note: We just send a prompt that should trigger tool use if possible, 
        # or we can inspect the session's tool list if the SDK permits.
        
        print("Sending prompt to test MCP tool discovery...")
        response = await wrapper.sdk_session.send_and_wait(
            {"prompt": "台積電今天的股價是多少？請使用搜尋工具。"}
        )
        
        print("\nAssistant Response:")
        print(response.data.content)
        
        # In a real scenario, we'd check logs or events to see if tool.execution_start 
        # fired for an MCP tool.

    except Exception as e:
        print(f"Error during verification: {e}")
    finally:
        await client.stop()

if __name__ == "__main__":
    asyncio.run(verify_mcp_integration())
