import json

from g1_bobby_unitree_bridge.publish_plan import main


def test_publish_plan_cli_renders_ros2_real_plan(capsys) -> None:
    exit_code = main(
        [
            "--transport",
            "ros2_real",
            "--command-json",
            '{"type":"move_velocity","seq":3,"timestamp":123.0,"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.2,"duration_ms":100}}',
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["transport"] == "ros2_real"
    assert payload["plans"][0]["plan"]["topic"] == "/lowcmd"
    assert payload["plans"][0]["plan"]["payload"]["duration_ms"] == 100


def test_publish_plan_cli_renders_sdk_real_plan(capsys) -> None:
    exit_code = main(
        [
            "--transport",
            "sdk_real",
            "--command-json",
            '{"type":"set_mode","seq":1,"timestamp":123.0,"payload":{"mode":"manual"}}',
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["transport"] == "sdk_real"
    assert payload["plans"][0]["plan"]["binding_target"] == "SportClient/basic service request"
    assert payload["plans"][0]["plan"]["payload"]["operation"] == "switch_mode"


def test_publish_plan_cli_rejects_unbound_command(capsys) -> None:
    exit_code = main(
        [
            "--transport",
            "ros2_real",
            "--command-json",
            '{"type":"heartbeat","seq":5,"timestamp":123.0,"payload":{"client_id":"test-client"}}',
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "no confirmed publish-plan binding for command type: heartbeat" in captured.err
