from src.tools.base import BaseTool

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
