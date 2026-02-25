import asyncio
from src.tools.registry import ToolRegistry
r = ToolRegistry()
asyncio.run(r.refresh())
