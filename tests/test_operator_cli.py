from pathlib import Path

import pytest

from g1_bobby_operator_cli.messages import (
    attach_token,
    demo_messages,
    load_jsonl_messages,
    refresh_message_timestamps,
)


def test_attach_token_adds_query_token() -> None:
    assert (
        attach_token("ws://localhost:8010/ws/operator", "secret")
        == "ws://localhost:8010/ws/operator?token=secret"
    )


def test_attach_token_replaces_existing_token_and_preserves_query() -> None:
    assert (
        attach_token("ws://localhost:8010/ws/operator?token=old&client=quest", "new")
        == "ws://localhost:8010/ws/operator?token=new&client=quest"
    )


def test_demo_messages_are_safe_manual_nudge_sequence() -> None:
    messages = demo_messages(client_id="quest-test", now=100.0)

    assert [message["seq"] for message in messages] == [1, 2, 3, 4]
    assert [message["type"] for message in messages] == [
        "heartbeat",
        "set_mode",
        "move_velocity",
        "stop",
    ]
    assert messages[0]["payload"]["client_id"] == "quest-test"
    assert messages[2]["payload"]["linear_x"] == 0.1
    assert messages[2]["timestamp"] == 100.02


def test_load_jsonl_messages(tmp_path: Path) -> None:
    script = tmp_path / "operator.jsonl"
    script.write_text(
        '{"type":"heartbeat","seq":1,"timestamp":1.0,"payload":{"client_id":"quest"}}\n\n',
        encoding="utf-8",
    )

    messages = load_jsonl_messages(script)

    assert len(messages) == 1
    assert messages[0]["type"] == "heartbeat"


def test_load_jsonl_messages_rejects_invalid_json(tmp_path: Path) -> None:
    script = tmp_path / "operator.jsonl"
    script.write_text("{bad-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        load_jsonl_messages(script)


def test_refresh_message_timestamps_copies_messages() -> None:
    original = [{"type": "heartbeat", "timestamp": 1.0}]

    refreshed = refresh_message_timestamps(original, now=200.0, step_s=0.5)

    assert refreshed == [{"type": "heartbeat", "timestamp": 200.0}]
    assert original == [{"type": "heartbeat", "timestamp": 1.0}]
