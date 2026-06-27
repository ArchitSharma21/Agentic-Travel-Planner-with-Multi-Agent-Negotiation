from __future__ import annotations

import json
import os
import threading
from datetime import date
from typing import Any

from app.config import settings


_lock = threading.Lock()


class UsageLimitExceeded(RuntimeError):
    pass


def _today() -> str:
    return date.today().isoformat()


def _empty_state() -> dict[str, Any]:
    return {
        "gemini_server_calls": {
            "date": _today(),
            "count": 0,
        }
    }


def _read_state() -> dict[str, Any]:
    path = settings.usage_state_path
    if not path or not os.path.exists(path):
        return _empty_state()

    try:
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_state()

    usage = state.setdefault("gemini_server_calls", {})
    if usage.get("date") != _today():
        usage["date"] = _today()
        usage["count"] = 0
    else:
        usage["count"] = int(usage.get("count") or 0)

    return state


def _write_state(state: dict[str, Any]) -> None:
    path = settings.usage_state_path
    if not path:
        return

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    os.replace(tmp_path, path)


def _limit() -> int:
    return max(0, settings.server_gemini_daily_call_limit)


def _limit_message(count: int, required_calls: int = 1) -> str:
    limit = _limit()
    remaining = max(0, limit - count)
    if required_calls > 1 and remaining > 0:
        return (
            "The shared Gemini key for this project is almost used up today "
            f"({count}/{limit} calls used, {required_calls} needed for a full plan). "
            "Please paste your own API key in the API Key field to continue with no project limit."
        )

    return (
        "The shared Gemini key for this project has reached today's limit "
        f"({count}/{limit} calls). Please paste your own API key in the API Key field "
        "to continue with no project limit."
    )


def ensure_gemini_server_budget(required_calls: int = 1) -> None:
    limit = _limit()
    if limit == 0:
        return

    with _lock:
        state = _read_state()
        usage = state["gemini_server_calls"]
        count = int(usage.get("count") or 0)

        if count + required_calls > limit:
            raise UsageLimitExceeded(_limit_message(count, required_calls))


def record_gemini_server_call() -> None:
    limit = _limit()
    if limit == 0:
        return

    with _lock:
        state = _read_state()
        usage = state["gemini_server_calls"]
        count = int(usage.get("count") or 0)

        if count + 1 > limit:
            raise UsageLimitExceeded(_limit_message(count))

        usage["count"] = count + 1
        _write_state(state)
