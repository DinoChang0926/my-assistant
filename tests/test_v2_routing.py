import sys
import os
from unittest.mock import MagicMock

# Create a mock for src.config BEFORE importing anything else
mock_settings = MagicMock()
mock_settings.COPILOT_GITHUB_TOKEN = "dummy"
mock_settings.COPILOT_MODEL = "claude-3.5-sonnet"
mock_settings.COPILOT_EVOLUTION_MODEL = "claude-3.5-sonnet"

sys.modules["src.config"] = MagicMock(settings=mock_settings)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from src.brain.router import IntentClassifier
from src.core.events import AgentEvent
from src.core.roles import RoleRegistry

async def test_routing():
    router = IntentClassifier()
    
    test_cases = [
        ("你好，今天天氣如何？", "general", RoleRegistry.SUPERVISOR),
        ("幫我寫一個 Python 費氏數列程式", "coding", RoleRegistry.CODER_GENERAL),
        ("我需要設計一個系統架構圖", "architecture", RoleRegistry.ARCHITECT_STRICT),
        ("幫我建立一個發信的工具，使用 create_tool", "evolution", RoleRegistry.EVOLUTION_MECHANIC),
    ]
    
    print("\n=== Testing Router Logic ===")
    for content, expected_intent, expected_role in test_cases:
        event = AgentEvent(session_id="test", content=content)
        config = await router.route(event)
        
        print(f"Input: {content}")
        print(f"  Result Intent: {config.intent} (Expected: {expected_intent})")
        print(f"  Result Role: {config.role.role_id if config.role else 'None'} (Expected: {expected_role.role_id})")
        print(f"  Prompt is None? {config.system_prompt is None}")
        
        assert config.intent == expected_intent
        assert config.role.role_id == expected_role.role_id
        
        if expected_role.system_prompt is None:
            assert config.system_prompt is None
        else:
            assert config.system_prompt is not None

    print("\n✅ All routing tests passed!")

if __name__ == "__main__":
    asyncio.run(test_routing())
