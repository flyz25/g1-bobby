import json

from g1_bobby_unitree_bridge.diagnostic_cli import main


def test_diagnostic_report_cli_renders_templates_and_probe(monkeypatch, capsys) -> None:
    async def fake_report(**kwargs):
        assert kwargs["transport"] == "sdk_real"
        assert kwargs["network_interface"] == "eth0"
        assert kwargs["probe_lowcmd_write"] is True
        return {
            "status": "blocked",
            "checks": {"dds_interface": "eth0"},
            "errors": [],
            "transport_capability": {"transport": "sdk_real", "ready": False},
            "lowcmd_templates": [{"name": "neutral_probe", "defaults": {"topic": "rt/lowcmd"}}],
            "lowcmd_write_probe": {"status": "rejected", "topic": "rt/lowcmd", "write_result": False},
        }

    monkeypatch.setattr(
        "g1_bobby_unitree_bridge.diagnostic_cli.build_unitree_diagnostic_report",
        fake_report,
    )

    exit_code = main(
        [
            "--transport",
            "sdk_real",
            "--network-interface",
            "eth0",
            "--probe-lowcmd-write",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["transport_capability"]["transport"] == "sdk_real"
    assert payload["lowcmd_templates"][0]["name"] == "neutral_probe"
    assert payload["lowcmd_write_probe"]["status"] == "rejected"
