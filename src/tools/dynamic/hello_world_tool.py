from src.tools.base import BaseTool

class HelloWorldTool(BaseTool):
    @property
    def name(self) -> str:
        return "hello_world"
    
    @property
    def description(self) -> str:
        return "Say hello to the user with a custom message."
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Greeting message"}
            },
            "required": ["message"]
        }

    async def execute(self, **kwargs) -> dict:
        msg = kwargs.get("message", "World")
        print(f"HelloWorldTool executed: {msg}")
        return {"result": f"Hello, {msg}!", "status": "success"}
