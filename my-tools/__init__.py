# my-tools: Independent tool package for AI Agent
# Phase 1: Code separation (Monorepo sub-directory)
# Phase 2: MCP stdio server (see server.py)
# Phase 3a: Atomic tools migrated to @define_tool + Pydantic (2026-02-28)
#
# Convention for @define_tool modules:
#   EXPORTED_TOOLS: list[Tool]  – list of @define_tool decorated functions
#   TOOL_CATEGORY: str          – category name applied to all tools in the module
#
# ⚠️ Remaining Tech Debt:
#   - secret_manager still `from src.utils.secret_manager import SecretManager` (reverse dep)
#   - send_telegram_buttons still uses BaseTool (needs runtime status_callback injection)
#   - Phase 3b should implement MCP Server to fully decouple tools from src/
