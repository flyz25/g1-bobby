from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_WS_URL = "ws://localhost:8010/ws/operator"
DEFAULT_OPERATOR_TOKEN = "dev-operator-token"


def attach_token(url: str, token: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["token"] = token
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        )
    )


def demo_messages(client_id: str = "operator-cli", now: float | None = None) -> list[dict[str, Any]]:
    base_time = time() if now is None else now
    return [
        {
            "type": "heartbeat",
            "seq": 1,
            "timestamp": base_time,
            "payload": {"client_id": client_id},
        },
        {
            "type": "set_mode",
            "seq": 2,
            "timestamp": base_time + 0.01,
            "payload": {"mode": "manual"},
        },
        {
            "type": "move_velocity",
            "seq": 3,
            "timestamp": base_time + 0.02,
            "payload": {
                "linear_x": 0.1,
                "linear_y": 0.0,
                "angular_z": 0.0,
                "duration_ms": 100,
            },
        },
        {
            "type": "stop",
            "seq": 4,
            "timestamp": base_time + 0.03,
            "payload": {"reason": "operator_cli_stop"},
        },
    ]


def load_jsonl_messages(path: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        messages.append(payload)
    return messages


def refresh_message_timestamps(
    messages: list[dict[str, Any]],
    now: float | None = None,
    step_s: float = 0.01,
) -> list[dict[str, Any]]:
    base_time = time() if now is None else now
    refreshed: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        copied = dict(message)
        copied["timestamp"] = base_time + (index * step_s)
        refreshed.append(copied)
    return refreshed
