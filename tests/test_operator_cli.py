import argparse
from pathlib import Path

import pytest

from g1_bobby_operator_cli.main import (
    build_outbound_messages,
    can_retry,
    effective_listen_s,
    format_event,
    resolve_ws_url,
    should_replay_messages,
    should_retry,
)
from g1_bobby_operator_cli.messages import (
    attach_token,
    default_audit_url,
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


def test_default_audit_url_appends_audit_suffix() -> None:
    assert default_audit_url("ws://localhost:8010/ws/operator") == "ws://localhost:8010/ws/operator/audit"
    assert (
        default_audit_url("ws://localhost:8010/ws/operator?token=old")
        == "ws://localhost:8010/ws/operator/audit?token=old"
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


def test_format_event_summarizes_state_with_unitree_projection() -> None:
    rendered = format_event(
        '{"type":"state","state":{"connected":true,"mode":"manual","estop_engaged":false,'
        '"pose_label":"unitree-g1 x=0.00 y=0.00 z=1.20"},'
        '"unitree_state":{"status":"receiving","source":"live","stale":false,'
        '"sample_counts":{"low_state":12,"sport_mode_state":13}}}'
    )

    assert rendered == (
        "state connected=True mode=manual estop=False pose=unitree-g1 x=0.00 y=0.00 z=1.20 "
        "[unitree=receiving source=live low=12 sport=13]"
    )


def test_format_event_summarizes_telemetry() -> None:
    rendered = format_event(
        '{"type":"telemetry","accepted_commands":3,"rejected_commands":1,'
        '"state":{"mode":"manual","pose_label":"unitree-g1 x=0.00 y=0.00 z=1.20"},'
        '"unitree_state":{"status":"receiving","source":"restored","stale":true,'
        '"sample_counts":{"low_state":8,"sport_mode_state":9}}}'
    )

    assert rendered == (
        "telemetry accepted=3 rejected=1 mode=manual pose=unitree-g1 x=0.00 y=0.00 z=1.20 "
        "[unitree=receiving source=restored stale=true low=8 sport=9]"
    )


def test_format_event_summarizes_ack_and_reject() -> None:
    assert format_event(
        '{"type":"ack","seq":7,"command_type":"move_velocity","message":"accepted",'
        '"unitree_command_plan":{"event_id":11,"recorded_at":123.0,"source":"restored","stale":true,'
        '"plan":{"seq":7,"type":"move_velocity","transport":"dry_run",'
        '"action":"motion.velocity","unitree_target":"base_velocity",'
        '"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.0,"duration_ms":100}}},'
        '"unitree_execution_plan":{"event_id":12,"recorded_at":124.0,"source":"live","stale":false,'
        '"execution_plan":{"transport":"ros2_plan_stub","command_type":"move_velocity","binding_mode":"low_level_motor",'
        '"surface":"LowCmd","target":"/lowcmd","payload":{"duration_ms":100},"note":"n"}}}'
    ) == (
        "ack seq=7 command=move_velocity message=accepted "
        "[id=11 action=motion.velocity target=base_velocity source=restored stale=true]"
        " [exec_id=12 transport=ros2_plan_stub exec_target=/lowcmd]"
    )
    assert format_event('{"type":"reject","seq":8,"code":"safety_rejected","reason":"operator heartbeat is stale"}') == (
        "reject seq=8 code=safety_rejected reason=operator heartbeat is stale"
    )


def test_format_event_summarizes_command_plan_event() -> None:
    assert format_event(
        '{"type":"command_plan","unitree_command_plan":{"event_id":11,"recorded_at":123.0,"source":"restored","stale":true,'
        '"plan":{"seq":7,"type":"move_velocity","transport":"dry_run",'
        '"action":"motion.velocity","unitree_target":"base_velocity",'
        '"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.0,"duration_ms":100}}}}'
    ) == "command-plan id=11 seq=7 action=motion.velocity target=base_velocity source=restored stale=true"


def test_format_event_summarizes_rejected_command_event() -> None:
    assert format_event(
        '{"type":"rejected_command","rejected_command":{"event_id":12,"recorded_at":123.0,"source":"restored","stale":true,'
        '"command_type":"move_velocity","rejection":{"type":"reject","seq":9,"code":"safety_rejected",'
        '"reason":"operator heartbeat is stale"}}}'
    ) == (
        "rejected-command id=12 seq=9 code=safety_rejected command=move_velocity "
        "source=restored stale=true reason=operator heartbeat is stale"
    )


def test_format_event_summarizes_execution_plan_event() -> None:
    assert format_event(
        '{"type":"execution_plan","unitree_execution_plan":{"event_id":13,"recorded_at":123.0,"source":"restored","stale":true,'
        '"execution_plan":{"transport":"sdk_plan_stub","command_type":"set_mode","binding_mode":"sport_service",'
        '"surface":"request_response","target":"SportClient/basic service request","payload":{"operation":"switch_mode"},'
        '"note":"n"}}}'
    ) == (
        "execution-plan id=13 transport=sdk_plan_stub command=set_mode "
        "target=SportClient/basic service request source=restored stale=true"
    )


def test_format_event_can_preserve_raw_json() -> None:
    raw = '{"type":"ack","seq":1}'

    assert format_event(raw, raw=True) == raw


def test_build_outbound_messages_uses_telemetry_only_mode() -> None:
    args = argparse.Namespace(
        telemetry_only=True,
        audit_stream=False,
        script=None,
        keep_script_timestamps=False,
        client_id="quest-test",
    )

    assert build_outbound_messages(args) == []


def test_build_outbound_messages_uses_demo_when_not_telemetry_only() -> None:
    args = argparse.Namespace(
        telemetry_only=False,
        audit_stream=False,
        script=None,
        keep_script_timestamps=False,
        client_id="quest-test",
    )

    messages = build_outbound_messages(args)
    assert [message["type"] for message in messages] == [
        "heartbeat",
        "set_mode",
        "move_velocity",
        "stop",
    ]


def test_effective_listen_s_defaults_to_timeout_for_telemetry_only() -> None:
    args = argparse.Namespace(listen_s=0.0, telemetry_only=True, audit_stream=False, timeout_s=3.5)

    assert effective_listen_s(args) == 3.5


def test_effective_listen_s_prefers_explicit_value() -> None:
    args = argparse.Namespace(listen_s=1.25, telemetry_only=True, audit_stream=False, timeout_s=3.5)

    assert effective_listen_s(args) == 1.25


def test_should_retry_requires_watch_and_retryable_error() -> None:
    args = argparse.Namespace(watch=True)

    assert can_retry(OSError("boom")) is True
    assert should_retry(args, OSError("boom")) is True
    assert should_retry(argparse.Namespace(watch=False), OSError("boom")) is False
    assert should_retry(args, ValueError("boom")) is False


def test_should_replay_messages_skips_script_and_telemetry_only() -> None:
    assert should_replay_messages(argparse.Namespace(telemetry_only=False, audit_stream=False, script=None)) is True
    assert should_replay_messages(
        argparse.Namespace(telemetry_only=False, audit_stream=False, script=Path("script.jsonl"))
    ) is False
    assert should_replay_messages(argparse.Namespace(telemetry_only=True, audit_stream=False, script=None)) is False
    assert should_replay_messages(argparse.Namespace(telemetry_only=False, audit_stream=True, script=None)) is False


def test_resolve_ws_url_uses_audit_stream_url() -> None:
    args = argparse.Namespace(
        url="ws://localhost:8010/ws/operator",
        audit_url=None,
        audit_stream=True,
    )
    assert resolve_ws_url(args) == "ws://localhost:8010/ws/operator/audit"
    args.audit_url = "ws://localhost:8010/ws/custom-audit"
    assert resolve_ws_url(args) == "ws://localhost:8010/ws/custom-audit"
