import json
from pathlib import Path
from time import time

from g1_bobby_contracts.commands import (
    CommandType,
    EmergencyStopCommand,
    EmergencyStopPayload,
    HeartbeatCommand,
    HeartbeatPayload,
    MoveVelocityCommand,
    MoveVelocityPayload,
    SetModeCommand,
    SetModePayload,
    StopCommand,
    StopPayload,
)
from g1_bobby_unitree_bridge.command_dry_run import (
    load_jsonl_commands,
    main,
    translate_command,
)


def test_translate_move_velocity_command() -> None:
    translated = translate_command(
        MoveVelocityCommand(
            type=CommandType.MOVE_VELOCITY,
            seq=3,
            timestamp=time(),
            payload=MoveVelocityPayload(
                linear_x=0.1,
                linear_y=0.0,
                angular_z=0.2,
                duration_ms=150,
            ),
        )
    )

    assert translated == {
        "seq": 3,
        "type": "move_velocity",
        "transport": "dry_run",
        "action": "motion.velocity",
        "unitree_target": "base_velocity",
        "payload": {
            "linear_x": 0.1,
            "linear_y": 0.0,
            "angular_z": 0.2,
            "duration_ms": 150,
        },
    }


def test_translate_stop_and_estop_commands() -> None:
    stop = translate_command(
        StopCommand(
            type=CommandType.STOP,
            seq=4,
            timestamp=time(),
            payload=StopPayload(reason="operator_stop"),
        )
    )
    estop = translate_command(
        EmergencyStopCommand(
            type=CommandType.ESTOP,
            seq=5,
            timestamp=time(),
            payload=EmergencyStopPayload(reason="operator_estop"),
        )
    )

    assert stop["action"] == "motion.stop"
    assert stop["payload"]["linear_x"] == 0.0
    assert estop["action"] == "safety.estop"
    assert estop["payload"]["reason"] == "operator_estop"


def test_translate_heartbeat_and_set_mode_commands() -> None:
    heartbeat = translate_command(
        HeartbeatCommand(
            type=CommandType.HEARTBEAT,
            seq=1,
            timestamp=100.0,
            payload=HeartbeatPayload(client_id="quest"),
        )
    )
    set_mode = translate_command(
        SetModeCommand(
            type=CommandType.SET_MODE,
            seq=2,
            timestamp=time(),
            payload=SetModePayload(mode="manual"),
        )
    )

    assert heartbeat["action"] == "bridge.keepalive"
    assert heartbeat["payload"]["client_id"] == "quest"
    assert set_mode["action"] == "bridge.set_mode"
    assert set_mode["payload"]["mode"] == "manual"


def test_load_jsonl_commands_reads_objects(tmp_path: Path) -> None:
    script = tmp_path / "commands.jsonl"
    script.write_text(
        '{"type":"heartbeat","seq":1,"timestamp":1.0,"payload":{"client_id":"quest"}}\n',
        encoding="utf-8",
    )

    assert load_jsonl_commands(script) == [
        {"type": "heartbeat", "seq": 1, "timestamp": 1.0, "payload": {"client_id": "quest"}}
    ]


def test_main_accepts_command_json(capsys) -> None:
    exit_code = main(
        [
            "--command-json",
            json.dumps(
                {
                    "type": "stop",
                    "seq": 4,
                    "timestamp": 10.0,
                    "payload": {"reason": "operator_stop"},
                }
            ),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["command_count"] == 1
    assert payload["commands"][0]["action"] == "motion.stop"


def test_main_rejects_missing_input(capsys) -> None:
    exit_code = main([])

    assert exit_code == 2
    assert "provide --command-json or --script" in capsys.readouterr().err
