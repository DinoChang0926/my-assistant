
import os
import sys
import json
import logging
import subprocess
import urllib.request
import urllib.error
import uvicorn
import copilot
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
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.INFO)
logging.getLogger("copilot").setLevel(logging.DEBUG)

logger = logging.getLogger("src.main")
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

MCP_BASE_URL = "http://127.0.0.1:8001"
MCP_SSE_URL = f"{MCP_BASE_URL}/sse"
MCP_STATUS_URL = f"{MCP_BASE_URL}/status"


def _build_copilot_client() -> CopilotClient:
    """Create CopilotClient with SDK-version-compatible config."""
    env = os.environ.copy()
    token = settings.COPILOT_GITHUB_TOKEN

    # Newer SDK shape: CopilotClient(SubprocessConfig(...))
    if hasattr(copilot, "SubprocessConfig"):
        config = copilot.SubprocessConfig(
            github_token=token,
            env=env,
        )
        return CopilotClient(config)

    # Legacy SDK shape: CopilotClient({ ...options... })
    return CopilotClient({
        "github_token": token,
        "env": env,
    })


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
        req = urllib.request.Request(MCP_SSE_URL, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.status == 200

    try:
        return await asyncio.to_thread(_probe)
    except Exception:
        return False


async def _get_mcp_status(timeout_sec: float = 1.0):
    """Read MCP status endpoint when available."""

    def _probe():
        req = urllib.request.Request(MCP_STATUS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if resp.status != 200:
                return None
            payload = resp.read().decode("utf-8")
            return json.loads(payload)

    try:
        return await asyncio.to_thread(_probe)
    except Exception:
        return None


async def _is_mcp_ready(timeout_sec: float = 1.0) -> bool:
    """Check whether MCP is reachable and functionally healthy."""
    if not await _is_mcp_sse_healthy(timeout_sec=timeout_sec):
        return False

    status_payload = await _get_mcp_status(timeout_sec=timeout_sec)
    if status_payload is None:
        # Backward compatibility: older MCP may not expose /status yet.
        logger.info("[MCP] /status unavailable, fallback to SSE reachability.")
        return True

    if status_payload.get("status") == "ok":
        return True

    logger.warning(f"[MCP] /status returned non-ok payload: {status_payload}")
    return False


async def _launch_mcp_with_retry(max_attempts: int = 3, wait_seconds: float = 1.0):
    """Launch MCP process and retry health checks.

    Returns:
        tuple[mcp_process, mcp_available]
        - (Popen, True): launched and managed by this process
        - (None, True): external MCP is already healthy and will be reused
        - (None, False): MCP unavailable
    """
    for attempt in range(1, max_attempts + 1):
        try:
            process = _start_mcp_process()
        except Exception as e:
            logger.warning(f"[MCP] Launch failed on attempt {attempt}/{max_attempts}: {e}")
            await asyncio.sleep(wait_seconds)
            continue

        for _ in range(5):
            if await _is_mcp_ready(timeout_sec=1.0):
                if process.poll() is None:
                    logger.info("[MCP] SSE server is healthy (child process).")
                    return process, True
                logger.info("[MCP] Reusing external MCP service already running on port 8001.")
                return None, True

            if process.poll() is not None:
                logger.warning(f"[MCP] Process exited early with code {process.returncode}")
                break
            await asyncio.sleep(wait_seconds)

        try:
            if process.poll() is None:
                process.terminate()
        except Exception:
            pass
        await asyncio.sleep(wait_seconds)

    if await _is_mcp_ready(timeout_sec=1.0):
        logger.info("[MCP] External MCP is healthy. Continue without spawning child process.")
        return None, True

    return None, False


async def _log_mcp_status():
    """Fetch and log MCP /status details once at startup."""
    status = await _get_mcp_status(timeout_sec=2.0)
    if status is None:
        logger.warning("[MCP] /status endpoint unreachable — cannot confirm tool list.")
        return
    tools = status.get("tools", [])
    logger.info(
        f"[MCP] Status OK — transport={status.get('transport', '?')}, "
        f"tools_count={status.get('tools_count', '?')}, "
        f"tools={tools}"
    )

# Define lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize Client
    logger.info("AI Agent Initializing (Lifespan Startup)...")
    
    # Pass token explicitly to avoid interactive prompt crash
    client = _build_copilot_client()
    await client.start()

    logger.info("Starting MCP SSE Server...")
    mcp_process, mcp_available = await _launch_mcp_with_retry(max_attempts=3, wait_seconds=1.0)
    app.state.mcp_available = mcp_available

    if not mcp_available:
        logger.warning("[MCP] SSE server unavailable after retries. Running in degraded mode.")
    else:
        if mcp_process is None:
            logger.info("[MCP] Using existing external MCP instance.")
        await _log_mcp_status()

    telegram_bot = None
    scheduler = None
    session_manager = None

    # 2. Setup Components
    try:
        session_manager = SessionManager(client)

        # --- MCP Monitor (needs session_manager for promote_degraded_sessions) ---
        async def _monitor_mcp() -> None:
            nonlocal mcp_process, mcp_available
            was_available = mcp_available
            # Give MCP extra time to stabilise after startup before first check
            await asyncio.sleep(10)
            fail_streak = 0
            while True:
                healthy = False
                if mcp_process is not None and mcp_process.poll() is None:
                    healthy = await _is_mcp_ready(timeout_sec=2.0)
                elif mcp_process is None:
                    healthy = await _is_mcp_ready(timeout_sec=2.0)

                if healthy:
                    fail_streak = 0
                    if not was_available:
                        logger.info("[MCP] Recovered. Promoting degraded sessions.")
                        session_manager.promote_degraded_sessions()
                        await _log_mcp_status()
                    mcp_available = True
                    app.state.mcp_available = True
                    was_available = True
                    await asyncio.sleep(15)
                    continue

                # Unhealthy path
                fail_streak += 1
                if fail_streak == 1:
                    logger.warning("[MCP] Health check failed. Will retry before restarting...")
                    await asyncio.sleep(5)
                    continue

                logger.warning(f"[MCP] Unavailable (streak={fail_streak}). Attempting restart...")
                was_available = False
                if mcp_process is not None and mcp_process.poll() is None:
                    try:
                        mcp_process.terminate()
                    except Exception:
                        pass
                    mcp_process = None

                mcp_process, mcp_available = await _launch_mcp_with_retry(max_attempts=2, wait_seconds=1.0)
                app.state.mcp_available = mcp_available
                if mcp_available:
                    logger.info("[MCP] Restart successful. Promoting degraded sessions.")
                    session_manager.promote_degraded_sessions()
                    await _log_mcp_status()
                    was_available = True
                    fail_streak = 0
                else:
                    logger.warning("[MCP] Restart failed. Keep degraded mode.")

                await asyncio.sleep(10)

        mcp_monitor_task = asyncio.create_task(_monitor_mcp())

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
        logger.info(f"[System] Registered Meta-Skills with DI: {task_status_instance.name}, {cancel_task_instance.name}")
        
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
                logger.info("Telegram Bot started in main event loop.")
                
                # 5. Initialize & Start Scheduler
                scheduler = SchedulerService(telegram_bot)
                await scheduler.start()
                logger.info("Scheduler Service started.")
            except Exception as t_err:
                logger.warning(f"Telegram Bot failed to start: {t_err}")
                logger.warning("Continuing without Telegram Bot... You can still use the REST API.")
                telegram_bot = None
        
        logger.info("AI Agent Components Initialized.")
        
        yield
        
    except Exception as e:
        logger.error(f"Fatal Error during startup: {e}", exc_info=True)
        logger.warning("Startup had errors. Service remains alive in degraded mode.")
        yield
    
    # Shutdown logic
    logger.info("AI Agent Shutting Down (Lifespan Shutdown)...")
    try:
        if 'mcp_monitor_task' in locals() and mcp_monitor_task:
            mcp_monitor_task.cancel()
            await asyncio.gather(mcp_monitor_task, return_exceptions=True)
    except Exception as e:
        logger.warning(f"Error stopping MCP monitor: {e}")
    try:
        if 'mcp_process' in locals() and mcp_process:
            mcp_process.terminate()
            logger.info("MCP SSE Server terminated.")
    except Exception as e:
        logger.warning(f"Error terminating MCP process: {e}")
    try:
        if telegram_bot:
            await telegram_bot.stop()
    except Exception as e:
        logger.warning(f"Error stopping telegram: {e}")
    try:
        if 'scheduler' in locals() and scheduler:
            await scheduler.stop()
    except Exception as e:
        logger.warning(f"Error stopping scheduler: {e}")
    try:
        await session_manager.cleanup_all()
    except Exception as e:
        logger.warning(f"Error cleaning sessions: {e}")
    try:
        if hasattr(client, 'stop'):
            await client.stop()
    except Exception as e:
        logger.warning(f"Error stopping client: {e}")

# Apply lifespan to the existing app from rest_api
rest_api.app.router.lifespan_context = lifespan
app = rest_api.app

if __name__ == "__main__":
    logger.info(f"Starting API Server on {settings.API_HOST}:{settings.API_PORT}...")
    # Run Uvicorn directly
    uvicorn.run(
        "src.main:app", 
        host=settings.API_HOST, 
        port=settings.API_PORT, 
        log_level=settings.LOG_LEVEL.lower(),
        reload=False
    )
