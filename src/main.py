
import os
import sys
import logging
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
    
    telegram_bot = None

    # 2. Setup Components
    try:
        session_manager = SessionManager(client)
        
        # Initialize Registry
        tool_registry = ToolRegistry()
        
        # Initialize Meta-Tools with Dependency Injection
        from .tools.static.create_tool import CreateToolTool
        from .tools.static.reload_tools import ReloadToolsTool
        from .tools.static.delegate_mechanic import DelegateToMechanicTool
        from .tools.static.task_control import TaskStatusTool, CancelTaskTool
        from src.brain.task_manager import task_manager
        
        create_tool_instance = CreateToolTool(registry=tool_registry)
        reload_tools_instance = ReloadToolsTool(registry=tool_registry)
        delegate_tool_instance = DelegateToMechanicTool(orchestrator=None, task_manager=task_manager)
        task_status_instance = TaskStatusTool(task_manager=task_manager)
        cancel_task_instance = CancelTaskTool(task_manager=task_manager)
        
        # Manually register DI tools
        tool_registry.register(create_tool_instance)
        tool_registry.register(reload_tools_instance)
        tool_registry.register(delegate_tool_instance)
        tool_registry.register(task_status_instance)
        tool_registry.register(cancel_task_instance)
        print(f"[System] Registered Meta-Skills with DI: {create_tool_instance.name}, {reload_tools_instance.name}, {delegate_tool_instance.name}, {task_status_instance.name}, {cancel_task_instance.name}")
        
        # Load other static and dynamic tools
        await tool_registry.refresh()
        
        orchestrator = TaskOrchestrator(session_manager, tool_registry)
        
        # Late binding for orchestrator
        delegate_tool_instance.orchestrator = orchestrator
        
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
        sys.exit(1)
    
    # Shutdown logic
    print("AI Agent Shutting Down (Lifespan Shutdown)...")
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
