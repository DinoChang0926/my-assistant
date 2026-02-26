import asyncio
from src.tools.registry import ToolRegistry

async def main():
    r = ToolRegistry()
    await r.refresh()
    dummy = r.get_tool("dummy")
    if dummy:
        print("----------")
        print("Executing dummy tool...")
        res = await dummy.execute(x=21)
        print("Result:", res)
        print("----------")
    else:
        print("Dummy tool not found")

if __name__ == "__main__":
    asyncio.run(main())
