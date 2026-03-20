from pathlib import Path
import sys

import pytest


_MY_TOOLS_DIR = Path(__file__).parent.parent / "my-tools"
if str(_MY_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_MY_TOOLS_DIR))

from atomic.static_tool_log_reader import log_reader


@pytest.mark.asyncio
async def test_log_reader_rejects_invalid_source():
    result = await log_reader(source="unknown")
    assert result["status"] == "error"
    assert "Invalid source" in result["message"]


@pytest.mark.asyncio
async def test_log_reader_debug_keyword_and_context(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    debug_log = tmp_path / "debug.log"
    debug_log.write_text(
        "line1\nline2\nERROR target failure\nline4\nline5\n",
        encoding="utf-8",
    )

    result = await log_reader(
        source="debug",
        mode="raw",
        keyword="target",
        context_lines=1,
        max_chars=2000,
    )
    assert result["status"] == "success"
    assert result["matched_count"] >= 1
    assert "ERROR target failure" in result["content"]


@pytest.mark.asyncio
async def test_log_reader_debug_truncation(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    debug_log = tmp_path / "debug.log"
    debug_log.write_text(("A" * 100 + "\n") * 200, encoding="utf-8")

    result = await log_reader(
        source="debug",
        mode="raw",
        tail_lines=150,
        max_chars=400,
    )
    assert result["status"] == "success"
    assert result["truncated"] is True
    assert len(result["content"]) <= 400


@pytest.mark.asyncio
async def test_log_reader_event_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    event_log = tmp_path / "event_log.json"
    event_log.write_text(
        """
[
  {"timestamp": "2026-03-20T12:00:00", "key": "k1", "value": "v1"},
  {"timestamp": "2026-03-20T12:01:00", "key": "k2", "value": "v2"}
]
""".strip(),
        encoding="utf-8",
    )

    result = await log_reader(source="event", mode="summary", max_chars=2000)
    assert result["status"] == "success"
    assert "k1" in result["content"] or "k2" in result["content"]


@pytest.mark.asyncio
async def test_log_reader_debug_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))

    result = await log_reader(source="debug", mode="summary")
    assert result["status"] == "not_found"
    assert result["source"] == "debug"
    assert "請確認服務已啟動並產生 log" in result["hint"]


@pytest.mark.asyncio
async def test_log_reader_masks_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    debug_log = tmp_path / "debug.log"
    debug_log.write_text(
        "bot123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ12345\n"
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456\n"
        "token=abcdefghijklmnopqrstuvwxyz123456\n",
        encoding="utf-8",
    )

    result = await log_reader(source="debug", mode="raw", tail_lines=20, max_chars=2000)
    assert result["status"] == "success"
    assert "bot***:***" in result["content"]
    assert "Authorization: Bearer ***" in result["content"]
    assert "token=***" in result["content"]


@pytest.mark.asyncio
async def test_log_reader_summary_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    debug_log = tmp_path / "debug.log"
    debug_log.write_text(
        "INFO start\n"
        "WARNING near limit\n"
        "ERROR failed once\n"
        "ERROR failed twice\n",
        encoding="utf-8",
    )

    result = await log_reader(source="debug", mode="summary", tail_lines=20, max_chars=2000)
    assert result["status"] == "success"
    assert "ERROR=2" in result["content"]
    assert "WARNING=1" in result["content"]
