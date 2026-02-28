import sys
import os
import uuid
from unittest.mock import MagicMock

# Create a mock for src.config BEFORE importing anything else
mock_settings = MagicMock()
mock_settings.COPILOT_GITHUB_TOKEN = "dummy"
mock_settings.COPILOT_MODEL = "claude-sonnet-4.5"
mock_settings.COPILOT_EVOLUTION_MODEL = "claude-sonnet-4.5"

sys.modules["src.config"] = MagicMock(settings=mock_settings)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from src.brain.router import IntentClassifier
from src.core.events import AgentEvent, InputSource
from src.core.roles import RoleRegistry

async def test_routing():
    """Router should classify into exactly 2 routes: architecture vs general.

    Phase 4 evaluation:
    - CODER_GENERAL removed (Supervisor delegates coding via tools).
    - EVOLUTION_MECHANIC invoked by delegate_to_mechanic tool, not router.
    - All non-architecture traffic → SUPERVISOR (general).
    """
    router = IntentClassifier()

    test_cases = [
        # General traffic → SUPERVISOR
        ("你好，今天天氣如何？", "general", RoleRegistry.SUPERVISOR),
        ("幫我寫一個 Python 費氏數列程式", "general", RoleRegistry.SUPERVISOR),
        ("幫我建立一個發信的工具，使用 create_tool", "general", RoleRegistry.SUPERVISOR),
        # Architecture keywords → ARCHITECT_STRICT
        ("我需要設計一個系統架構圖", "architecture", RoleRegistry.ARCHITECT_STRICT),
        ("幫我畫一個 mermaid 流程圖", "architecture", RoleRegistry.ARCHITECT_STRICT),
        ("顯示目錄結構", "architecture", RoleRegistry.ARCHITECT_STRICT),
    ]

    print("\n=== Testing Router Logic (Phase 4 Simplified) ===")
    for content, expected_intent, expected_role in test_cases:
        event = AgentEvent(
            event_id=str(uuid.uuid4()),
            source=InputSource.API,
            session_id="test",
            content=content,
        )
        config = await router.route(event)

        print(f"Input: {content}")
        print(f"  Intent: {config.intent} (expected: {expected_intent})")
        print(f"  Role:   {config.role.role_id} (expected: {expected_role.role_id})")

        assert config.intent == expected_intent
        assert config.role.role_id == expected_role.role_id
        assert config.system_prompt is not None  # Both roles have explicit prompts

    print("\n✅ All routing tests passed!")

if __name__ == "__main__":
    asyncio.run(test_routing())
