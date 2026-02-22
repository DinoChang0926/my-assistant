import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

@dataclass
class TaskRecord:
    id: str
    instruction: str
    status: str  # pending, running, done, cancelled, error
    started_at: datetime
    asyncio_task: Optional[asyncio.Task] = None
    result: Any = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "instruction": self.instruction,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "result": self.result,
            "error": self.error
        }

class TaskManager:
    """
    Central controller for background tasks (Sub-Agent delegations).
    Allows monitoring progress and cancelling tasks.
    """
    
    def __init__(self):
        self._tasks: Dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()

    async def register(self, task: TaskRecord):
        async with self._lock:
            self._tasks[task.id] = task

    async def get(self, task_id: str) -> Optional[TaskRecord]:
        async with self._lock:
            return self._tasks.get(task_id)

    async def list_active(self) -> List[TaskRecord]:
        async with self._lock:
            return [t for t in self._tasks.values() if t.status in ["pending", "running"]]

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            
            if task.status in ["done", "cancelled", "error"]:
                return False

            if task.asyncio_task and not task.asyncio_task.done():
                task.asyncio_task.cancel()
                task.status = "cancelled"
                return True
            
            return False

    async def update_status(self, task_id: str, status: str, result: Any = None, error: str = None):
        async with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = status
                if result is not None:
                    self._tasks[task_id].result = result
                if error is not None:
                    self._tasks[task_id].error = error

# Global Singleton
task_manager = TaskManager()
