from fastapi import FastAPI, HTTPException
from typing import Optional
from pydantic import BaseModel
from ..core.events import AgentEvent, InputSource, AgentResponse
from .gateway import UnifiedGateway
import uuid

app = FastAPI(title="AI Agent API")

# Dependency Placeholder (will be injected in main.py)
gateway: UnifiedGateway = None

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

def set_gateway(g: UnifiedGateway):
    global gateway
    gateway = g
