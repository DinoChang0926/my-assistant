"""Tests for local_memory tool path resolution and basic operations."""
import os
import sys
import json
import asyncio
import tempfile
from pathlib import Path

import pytest

# Ensure atomic module is importable by adding my-tools to sys.path
_MY_TOOLS_DIR = Path(__file__).parent.parent / "my-tools"
if str(_MY_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_MY_TOOLS_DIR))

from atomic.static_tool_local_memory import _get_file_path, local_memory


# ── Path resolution tests ──────────────────────────────────────────

class TestGetFilePath:
    """Verify _get_file_path honours STORAGE_PATH env var."""

    def test_uses_storage_path_env(self, tmp_path, monkeypatch):
        """When STORAGE_PATH is set, _get_file_path should use it."""
        monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
        result = _get_file_path("fact")
        assert result == tmp_path / "local_memory.json"

    def test_event_log_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
        result = _get_file_path("event")
        assert result == tmp_path / "event_log.json"

    def test_fallback_when_env_not_set(self, monkeypatch):
        """Without STORAGE_PATH, falls back to relative 'storage'."""
        monkeypatch.delenv("STORAGE_PATH", raising=False)
        result = _get_file_path("fact")
        assert result == Path("storage") / "local_memory.json"


# ── Functional tests ───────────────────────────────────────────────

class TestLocalMemoryTool:
    """End-to-end tests for local_memory async function."""

    @pytest.fixture(autouse=True)
    def _setup_storage(self, tmp_path, monkeypatch):
        monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
        self.storage = tmp_path

    @pytest.mark.asyncio
    async def test_set_and_get_fact(self):
        result = await local_memory(action="set", data_type="fact", key="user_name", value="Dino")
        assert result["status"] == "success"

        result = await local_memory(action="get", data_type="fact", key="user_name")
        assert result["status"] == "success"
        assert result["value"] == "Dino"

    @pytest.mark.asyncio
    async def test_list_facts(self):
        await local_memory(action="set", data_type="fact", key="k1", value="v1")
        result = await local_memory(action="list", data_type="fact")
        assert "k1" in result["keys"]

    @pytest.mark.asyncio
    async def test_delete_fact(self):
        await local_memory(action="set", data_type="fact", key="tmp", value="val")
        result = await local_memory(action="delete", data_type="fact", key="tmp")
        assert result["status"] == "success"

        result = await local_memory(action="get", data_type="fact", key="tmp")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_not_found(self):
        result = await local_memory(action="get", data_type="fact", key="nope")
        assert result["status"] == "not_found"
