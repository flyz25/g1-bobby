import json

from g1_bobby_unitree_bridge.lowcmd_experiments import main


def test_lowcmd_experiments_cli_renders_cases(monkeypatch, capsys) -> None:
    class FakePublisher:
        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

        async def publish_frame(self, *, template="neutral_probe"):
            return {
                "topic": "rt/lowcmd",
                "template": template,
                "mode_pr": 0,
                "mode_machine": 0,
                "motor_count": 35,
                "motor_mode": 0,
                "q": 0.0,
                "dq": 0.0,
                "tau": 0.0,
                "kp": 0.0,
                "kd": 0.0,
                "crc": 1,
                "write_result": template != "hold_zero_mode1",
            }

    monkeypatch.setattr(
        "g1_bobby_unitree_bridge.lowcmd_experiments.HgLowCmdProbePublisher",
        lambda **kwargs: FakePublisher(),
    )

    exit_code = main(
        [
            "--network-interface",
            "eth0",
            "--template",
            "neutral_probe",
            "--template",
            "hold_zero_mode1",
            "--period-s",
            "0",
            "--count",
            "2",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["accepted_cases"] == 1
    assert payload["total_cases"] == 2
    assert payload["cases"][1]["template"] == "hold_zero_mode1"
    assert payload["cases"][1]["accepted"] is False
