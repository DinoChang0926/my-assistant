# my-tools: Independent tool package for AI Agent
# Phase 1: Code separation (Monorepo sub-directory)
# Phase 2: MCP stdio server (see server.py)

# ⚠️ Known Tech Debt (Phase 2):
#   - Atomic tools still `from src.tools.base import BaseTool` (reverse dependency on src)
#   - schedule_reminder depends on `from src.config import settings`
#   - Phase 2 should extract BaseTool ABC into my-tools/base.py to break the coupling
