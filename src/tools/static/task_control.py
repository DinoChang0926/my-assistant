from datetime import datetime
from src.tools.base import BaseTool

class TaskStatusTool(BaseTool):
    """
    查詢目前背景任務的執行狀態。
    """
    
    def __init__(self, task_manager=None):
        self.task_manager = task_manager

    @property
    def name(self) -> str:
        return "task_status"

    @property
    def category(self) -> str:
        return "task_control"

    @property
    def description(self) -> str:
        return (
            "查詢背景委派任務的狀態。當使用者詢問進度時，主動呼叫此工具。\n"
            "如果不提供 task_id，將列出所有正在執行的任務。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "欲查詢的特定任務 ID (例如 'task_abc123')。留空則列出所有活動中任務。"
                }
            }
        }

    async def execute(self, **kwargs) -> dict:
        if not self.task_manager:
            return {"status": "error", "message": "TaskManager not injected."}
            
        task_id = kwargs.get("task_id")
        
        if task_id:
            record = await self.task_manager.get(task_id)
            if not record:
                return {"status": "error", "message": f"找不到任務 ID: {task_id}"}
            return {"status": "success", "task": record.to_dict()}
        else:
            active_tasks = await self.task_manager.list_active()
            return {
                "status": "success", 
                "active_tasks": [t.to_dict() for t in active_tasks],
                "summary": f"目前共有 {len(active_tasks)} 個任務正在執行中。"
            }

class CancelTaskTool(BaseTool):
    """
    隨時叫停正在進行中的背景委派任務。
    """
    
    def __init__(self, task_manager=None):
        self.task_manager = task_manager

    @property
    def name(self) -> str:
        return "cancel_task"

    @property
    def category(self) -> str:
        return "task_control"

    @property
    def description(self) -> str:
        return "取消特定 ID 的背景任務。當使用者明確表示「停、取消、不需要了」時，請呼叫此工具。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "欲取消的任務 ID (必填)。"
                },
                "reason": {
                    "type": "string",
                    "description": "取消的原因 (可選)。"
                }
            },
            "required": ["task_id"]
        }

    async def execute(self, **kwargs) -> dict:
        if not self.task_manager:
            return {"status": "error", "message": "TaskManager not injected."}
            
        task_id = kwargs.get("task_id")
        reason = kwargs.get("reason", "使用者主動取消")
        
        success = await self.task_manager.cancel(task_id)
        
        if success:
            status_callback = kwargs.get("status_callback")
            if status_callback:
                await status_callback(f"❌ [系統部] 任務 {task_id} 已由主助理叫停。原因：{reason}")
            
            return {"status": "success", "message": f"已成功中止任務 {task_id}"}
        else:
            return {"status": "error", "message": f"無法中止任務 {task_id} (可能 ID 錯誤或任務已結束)"}
