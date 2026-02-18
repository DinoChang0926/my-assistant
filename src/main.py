
import os
import sys
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from copilot import CopilotClient

from .config import settings
from .memory.manager import SessionManager
from .brain.router import IntentClassifier
from .brain.orchestrator import TaskOrchestrator
from .tools.registry import ToolRegistry
from .perception.gateway import UnifiedGateway
from .perception import rest_api
from .perception.telegram_bot import TelegramBot
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
    
    telegram_bot = None

    # 2. Setup Components
    try:
        session_manager = SessionManager(client)
        
        # Initialize Registry and Load Tools
        tool_registry = ToolRegistry()
        tool_registry.load_static_tools()
        tool_registry.load_dynamic_tools()
        
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
                await telegram_bot.initialize()
                
                # Run polling in separate thread to avoid event loop conflicts
                import threading
                bot_thread = threading.Thread(target=telegram_bot.run_in_thread, daemon=True)
                bot_thread.start()
                
            except Exception as e:
                print(f"Failed to start Telegram Bot: {e}")
        
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
        await session_manager.cleanup_all()
        if hasattr(client, 'stop'):
            await client.stop()
        
        if telegram_bot:
            await telegram_bot.stop()
            
    except Exception as e:
        print(f"Error during shutdown: {e}")

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
