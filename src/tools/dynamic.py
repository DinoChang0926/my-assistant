import asyncio
import json
import sys
from pathlib import Path
from src.tools.base import BaseTool

class SubprocessDynamicTool(BaseTool):
    """
    A dynamic tool that executes an independent CLI script in a subprocess.
    This prevents memory leaks, isolates the execution environment, and provides strict timeouts.
    """
    
    def __init__(self, name: str, category: str, description: str, parameters: dict, script_path: Path):
        self._name = name
        self._category = category
        self._description = description
        self._parameters = parameters
        self._script_path = script_path

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return self._category

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return self._parameters

    async def execute(self, **kwargs) -> dict:
        input_data = json.dumps(kwargs)
        
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(self._script_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=input_data.encode('utf-8')),
                    timeout=15.0  # 強制 15 秒超時
                )
            except asyncio.TimeoutError:
                process.kill()
                return {"status": "error", "message": "Tool execution timed out after 15 seconds. Process was killed."}
            
            if process.returncode != 0:
                err_text = stderr.decode('utf-8').strip()
                return {"status": "error", "message": f"Script failed with code {process.returncode}", "stderr": err_text}
                
            out_text = stdout.decode('utf-8').strip()
            if not out_text:
                return {"status": "error", "message": "Script produced no standard output."}
                
            try:
                # 嘗試解析最後一行或整個輸出為 JSON
                lines = [line.strip() for line in out_text.split('\n') if line.strip()]
                return json.loads(lines[-1] if lines else "{}")
            except json.JSONDecodeError:
                return {
                    "status": "error", 
                    "message": "Script did not return a valid JSON object on its final output line.",
                    "raw_output": out_text,
                    "stderr": stderr.decode('utf-8').strip()
                }

        except Exception as e:
            return {"status": "error", "message": f"Subprocess spawning failed: {str(e)}"}
