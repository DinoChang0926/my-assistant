from fastapi import FastAPI, HTTPException
from typing import Optional, Any
from pydantic import BaseModel
from src.core.events import AgentEvent, InputSource, AgentResponse
from src.perception.gateway import UnifiedGateway
import uuid

app = FastAPI(title="AI Agent API")

import logging
logger = logging.getLogger(__name__)

# Dependency Placeholder (will be injected in main.py)
gateway: UnifiedGateway = None
tool_registry: Any = None  # Injected

class ChatRequest(BaseModel):
    content: str
    session_id: Optional[str] = None

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/chat", response_model=AgentResponse)
async def chat(request: ChatRequest):
    if gateway is None:
        raise HTTPException(status_code=503, detail="Gateway not initialized")
    
    event = AgentEvent(
        event_id=str(uuid.uuid4()),
        source=InputSource.API,
        session_id=request.session_id or str(uuid.uuid4()),
        content=request.content
    )
    
    response = await gateway.process(event)
    return response

# Skills (Tools) Management Endpoints
@app.get("/skills")
async def list_skills():
    """List all available tools/skills with metadata."""
    if tool_registry is None:
        raise HTTPException(status_code=503, detail="ToolRegistry not initialized")
    
    # Return full schema for each tool to provide "how to use" info
    return {
        "total": len(tool_registry._tools),
        "skills": tool_registry.get_all_schemas()
    }

@app.post("/skills/reload")
async def reload_skills():
    """Trigger a hot-reload of all static and dynamic tools."""
    if tool_registry is None:
        raise HTTPException(status_code=503, detail="ToolRegistry not initialized")
    result = await tool_registry.refresh()
    return {
        "status": "success",
        "message": "Skills reloaded successfully",
        "data": result
    }

@app.get("/skills/{name}")
async def get_skill_details(name: str):
    """Get detailed schema for a specific skill."""
    if tool_registry is None:
        raise HTTPException(status_code=503, detail="ToolRegistry not initialized")
    tool = tool_registry.get_tool(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return tool.to_schema()

# Legacy Endpoints (Optional: Keep for backward compatibility or deprecate)
@app.post("/system/tools/refresh")
async def refresh_tools():
    return await reload_skills()

def set_gateway(g: UnifiedGateway):
    global gateway
    gateway = g

def set_tool_registry(r: Any):
    global tool_registry
    tool_registry = r
