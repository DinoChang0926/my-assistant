import json
import os
import re
from pathlib import Path
from typing import Dict, Tuple


DEFAULT_MAX_CHARS = 2000
MAX_MAX_CHARS = 4000
DEFAULT_TAIL_LINES = 50
MAX_TAIL_LINES = 150
DEFAULT_CONTEXT_LINES = 5
MAX_CONTEXT_LINES = 20


def _bounds(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _mask_secrets(text: str) -> str:
    text = re.sub(r"bot\d+:[A-Za-z0-9_-]{20,}", "bot***:***", text)
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._-]+", r"\1***", text)
    text = re.sub(r"(?i)(token\s*[=:]\s*)[A-Za-z0-9._-]{16,}", r"\1***", text)
    return text


def _truncate(text: str, max_chars: int) -> Tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[: max_chars - 3] + "...", True


def _resolve_paths() -> Dict[str, Path]:
    project_root = Path(__file__).resolve().parents[2]
    storage_path = Path(os.environ.get("STORAGE_PATH", str(project_root / "storage")))
    return {
        "debug": storage_path / "debug.log",
        "event": storage_path / "event_log.json",
        "diagnose": project_root / "scripts" / "diagnose_output.txt",
    }


def _read_text_lines(path: Path, max_bytes: int = 2_000_000) -> list:
    size = path.stat().st_size
    if size <= max_bytes:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()

    with open(path, "rb") as f:
        f.seek(-max_bytes, os.SEEK_END)
        chunk = f.read()

    text = chunk.decode("utf-8", errors="ignore")
    lines = text.splitlines()
    if lines:
        lines = lines[1:]
    return lines


def _build_event_summary(path: Path, tail_lines: int) -> Tuple[str, int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "event_log.json 格式不合法，無法解析。", 0

    if not isinstance(data, list) or not data:
        return "event_log.json 目前沒有事件資料。", 0

    recent = data[-min(tail_lines, len(data)) :]
    lines = []
    for entry in recent[-5:]:
        ts = str(entry.get("timestamp", ""))[:19]
        key = str(entry.get("key", ""))
        value = str(entry.get("value", "")).replace("\n", " ")[:120]
        lines.append(f"[{ts}] {key}: {value}")

    return "\n".join(lines), len(recent)


async def log_reader(
    source: str = "debug",
    mode: str = "summary",
    keyword: str = "",
    tail_lines: int = DEFAULT_TAIL_LINES,
    context_lines: int = DEFAULT_CONTEXT_LINES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict:
    """
    安全讀取除錯 log。支援來源：debug, diagnose, event。
    預設回傳摘要，避免一次輸出過量內容造成 session 膨脹。
    """
    source = (source or "debug").strip().lower()
    mode = (mode or "summary").strip().lower()
    keyword = (keyword or "").strip()

    if source not in {"debug", "diagnose", "event"}:
        return {
            "status": "error",
            "message": "Invalid source. Allowed: debug, diagnose, event.",
        }

    if mode not in {"summary", "raw"}:
        return {
            "status": "error",
            "message": "Invalid mode. Allowed: summary, raw.",
        }

    tail_lines = _bounds(int(tail_lines), 1, MAX_TAIL_LINES)
    context_lines = _bounds(int(context_lines), 0, MAX_CONTEXT_LINES)
    max_chars = _bounds(int(max_chars), 300, MAX_MAX_CHARS)

    paths = _resolve_paths()
    target = paths[source]

    if not target.exists():
        hint = "請先執行 scripts/diagnose_tools.py 產生診斷輸出。" if source == "diagnose" else "請確認服務已啟動並產生 log。"
        return {
            "status": "not_found",
            "source": source,
            "source_path": str(target),
            "matched_count": 0,
            "truncated": False,
            "content": "",
            "hint": hint,
        }

    if source == "event":
        summary, recent_count = _build_event_summary(target, tail_lines)
        content, truncated = _truncate(_mask_secrets(summary), min(max_chars, DEFAULT_MAX_CHARS if mode == "summary" else max_chars))
        return {
            "status": "success",
            "source": source,
            "source_path": str(target),
            "matched_count": recent_count,
            "truncated": truncated,
            "line_range": "events(last)",
            "content": content,
            "hint": "若需要完整排錯請改查 debug 或 diagnose。",
        }

    lines = _read_text_lines(target)
    total = len(lines)
    safe_limit = DEFAULT_MAX_CHARS if mode == "summary" else max_chars

    if keyword:
        lowered = keyword.lower()
        hit_indexes = [i for i, line in enumerate(lines) if lowered in line.lower()]
        if not hit_indexes:
            tail = lines[-tail_lines:]
            summary = "\n".join(tail[-5:]) if tail else "(no content)"
            content, truncated = _truncate(_mask_secrets(summary), safe_limit)
            return {
                "status": "success",
                "source": source,
                "source_path": str(target),
                "matched_count": 0,
                "truncated": truncated,
                "line_range": f"{max(1, total - len(tail) + 1)}-{total}" if total else "0-0",
                "content": content,
                "hint": "未命中關鍵字，已回傳尾端摘要。",
            }

        chunks = []
        for idx in hit_indexes[:5]:
            start = max(0, idx - context_lines)
            end = min(total, idx + context_lines + 1)
            chunks.append(f"--- match line {idx + 1} ---")
            chunks.extend(lines[start:end])

        content_text = "\n".join(chunks)
        content, truncated = _truncate(_mask_secrets(content_text), safe_limit)
        return {
            "status": "success",
            "source": source,
            "source_path": str(target),
            "matched_count": len(hit_indexes),
            "truncated": truncated,
            "line_range": f"1-{total}" if total else "0-0",
            "content": content,
            "hint": "若仍需更多內容，請縮小 keyword 或降低 context_lines。",
        }

    tail = lines[-tail_lines:]
    if mode == "summary":
        error_count = sum(1 for ln in tail if "ERROR" in ln)
        warning_count = sum(1 for ln in tail if "WARNING" in ln)
        last_line = next((ln for ln in reversed(tail) if ln.strip()), "(empty)")
        summary = (
            f"source={source} total_lines={total} tail={len(tail)}\n"
            f"ERROR={error_count} WARNING={warning_count}\n"
            f"last_line={last_line[:220]}"
        )
        content, truncated = _truncate(_mask_secrets(summary), safe_limit)
    else:
        raw = "\n".join(tail)
        content, truncated = _truncate(_mask_secrets(raw), safe_limit)

    start_line = max(1, total - len(tail) + 1) if total else 0
    return {
        "status": "success",
        "source": source,
        "source_path": str(target),
        "matched_count": 0,
        "truncated": truncated,
        "line_range": f"{start_line}-{total}" if total else "0-0",
        "content": content,
        "hint": "建議先用 summary，再用 keyword + raw 逐步展開。",
    }
