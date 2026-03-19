import sys
sys.path.insert(0, 'my-tools')
import asyncio
from server import mcp
import json

async def main():
    tools = await mcp.list_tools()
    problem_tools = []
    for t in tools:
        if "anyOf" in json.dumps(t.inputSchema):
            problem_tools.append(t.name)
    print("Tools with anyOf:", problem_tools)

if __name__ == "__main__":
    asyncio.run(main())
