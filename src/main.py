
import os
import sys
import logging
import subprocess
import urllib.request
import urllib.error
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

# 建立 storage 目錄
os.makedirs("storage", exist_ok=True)

# 提前載入設定，以便 logging level 可依 .env 的 LOG_LEVEL 設定調整
from src.config import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("storage/debug.log", encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
# 過濾底層雜訊
logging.getLogger("httpcore").setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("telegram").setLevel(logging.INFO)
logging.getLogger("copilot").setLevel(logging.DEBUG)
from copilot import CopilotClient
from src.memory.manager import SessionManager
from src.brain.router import IntentClassifier
from src.brain.orchestrator import TaskOrchestrator
from src.tools.registry import ToolRegistry
from src.perception.gateway import UnifiedGateway
from src.perception import rest_api
from src.perception.telegram_bot import TelegramBot
from src.perception.scheduler import SchedulerService
import asyncio


def _start_mcp_process() -> subprocess.Popen:
    """Start MCP server in SSE mode as a child process."""
    storage_path = os.path.abspath(settings.SESSION_STORAGE_PATH)
    env = {
        **os.environ,
        "PYTHONPATH": os.getcwd(),
        "STORAGE_PATH": storage_path,
    }
    return subprocess.Popen(
        [sys.executable, "my-tools/server.py", "--sse"],
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


async def _is_mcp_sse_healthy(timeout_sec: float = 1.0) -> bool:
    """Probe MCP SSE endpoint to determine whether it is accepting connections."""

    def _probe() -> bool:
        req = urllib.request.Request("http://127.0.0.1:8001/sse", method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.status == 200

    try:
        return await asyncio.to_thread(_probe)
    except Exception:
        return False


async def _launch_mcp_with_retry(max_attempts: int = 3, wait_seconds: float = 1.0):
    """Launch MCP process and retry health checks. Returns process or None."""
    for attempt in range(1, max_attempts + 1):
        try:
            process = _start_mcp_process()
        except Exception as e:
            print(f"[MCP] Launch failed on attempt {attempt}/{max_attempts}: {e}")
            await asyncio.sleep(wait_seconds)
            continue

        for _ in range(5):
            if process.poll() is not None:
                print(f"[MCP] Process exited early with code {process.returncode}")
                break
            if await _is_mcp_sse_healthy(timeout_sec=1.0):
                print("[MCP] SSE server is healthy.")
                return process
            await asyncio.sleep(wait_seconds)

        try:
            if process.poll() is None:
                process.terminate()
        except Exception:
            pass
        await asyncio.sleep(wait_seconds)

    return None

# Define lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize Client
    print("AI Agent Initializing (Lifespan Startup)...")
    
    # Pass token explicitly to avoid interactive prompt crash
    client = CopilotClient({
        "github_token": settings.COPILOT_GITHUB_TOKEN,
        "env": os.environ.copy()
    })
    await client.start()

    print("Starting MCP SSE Server...")
    mcp_process = await _launch_mcp_with_retry(max_attempts=3, wait_seconds=1.0)
    mcp_available = mcp_process is not None
    app.state.mcp_available = mcp_available

    if not mcp_available:
        print("⚠️ MCP SSE server unavailable. Running in degraded mode (main flow stays alive).")

    async def _monitor_mcp() -> None:
        nonlocal mcp_process, mcp_available
        while True:
            await asyncio.sleep(5)
            if mcp_process is not None and mcp_process.poll() is None:
                continue

            print("[MCP] Detected unavailable process. Attempting restart...")
            mcp_process = await _launch_mcp_with_retry(max_attempts=2, wait_seconds=1.0)
            mcp_available = mcp_process is not None
            app.state.mcp_available = mcp_available
            if mcp_available:
                print("[MCP] Restart successful.")
            else:
                print("[MCP] Restart failed. Keep degraded mode.")

    mcp_monitor_task = asyncio.create_task(_monitor_mcp())

    telegram_bot = None
    scheduler = None
    session_manager = None

    # 2. Setup Components
    try:
        session_manager = SessionManager(client)
        
        # Initialize Registry
        tool_registry = ToolRegistry()
        
        # Initialize Meta-Tools with Dependency Injection
        from .tools.static.task_control import TaskStatusTool, CancelTaskTool
        from src.brain.task_manager import task_manager
        
        task_status_instance = TaskStatusTool(task_manager=task_manager)
        cancel_task_instance = CancelTaskTool(task_manager=task_manager)
        
        # Manually register DI tools
        tool_registry.register(task_status_instance)
        tool_registry.register(cancel_task_instance)
        print(f"[System] Registered Meta-Skills with DI: {task_status_instance.name}, {cancel_task_instance.name}")
        
        # Load other static and dynamic tools
        await tool_registry.refresh()
        
        orchestrator = TaskOrchestrator(session_manager, tool_registry)
        
        router = IntentClassifier()
        gateway = UnifiedGateway(router, orchestrator)
        
        # 3. Inject Dependency
        rest_api.set_gateway(gateway)
        rest_api.set_tool_registry(tool_registry)
        
        # 4. Initialize Telegram Bot
        if settings.TELEGRAM_BOT_TOKEN:
            try:
                telegram_bot = TelegramBot(gateway)
                await telegram_bot.start_bot()
                print("Telegram Bot started in main event loop.")
                
                # 5. Initialize & Start Scheduler
                scheduler = SchedulerService(telegram_bot)
                await scheduler.start()
                print("Scheduler Service started.")
            except Exception as t_err:
                print(f"⚠️ Telegram Bot failed to start: {t_err}")
                print("Continuing without Telegram Bot... You can still use the REST API.")
                telegram_bot = None
        
        print("AI Agent Components Initialized.")
        
        yield
        
    except Exception as e:
        print(f"Fatal Error during startup: {e}")
        import traceback
        traceback.print_exc()
        print("⚠️ Startup had errors. Service remains alive in degraded mode.")
        yield
    
    # Shutdown logic
    print("AI Agent Shutting Down (Lifespan Shutdown)...")
    try:
        if 'mcp_monitor_task' in locals() and mcp_monitor_task:
            mcp_monitor_task.cancel()
            await asyncio.gather(mcp_monitor_task, return_exceptions=True)
    except Exception as e:
        print(f"Error stopping MCP monitor: {e}")
    try:
        if 'mcp_process' in locals() and mcp_process:
            mcp_process.terminate()
            print("MCP SSE Server terminated.")
    except Exception as e:
        print(f"Error terminating MCP process: {e}")
    try:
        if telegram_bot:
            await telegram_bot.stop()
    except Exception as e:
        print(f"Error stopping telegram: {e}")
    try:
        if 'scheduler' in locals() and scheduler:
            await scheduler.stop()
    except Exception as e:
        print(f"Error stopping scheduler: {e}")
    try:
        await session_manager.cleanup_all()
    except Exception as e:
        print(f"Error cleaning sessions: {e}")
    try:
        if hasattr(client, 'stop'):
            await client.stop()
    except Exception as e:
        print(f"Error stopping client: {e}")

# Apply lifespan to the existing app from rest_api
rest_api.app.router.lifespan_context = lifespan
app = rest_api.app

if __name__ == "__main__":
    print(f"Starting API Server on {settings.API_HOST}:{settings.API_PORT}...")
    # Run Uvicorn directly
    uvicorn.run(
        "src.main:app", 
        host=settings.API_HOST, 
        port=settings.API_PORT, 
        log_level=settings.LOG_LEVEL.lower(),
        reload=False
    )
