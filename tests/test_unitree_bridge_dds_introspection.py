import json

from g1_bobby_unitree_bridge.dds_introspection_cli import main


def test_dds_introspection_cli_renders_known_surfaces(monkeypatch, capsys) -> None:
    async def fake_report(**kwargs):
        return {
            "status": "blocked",
            "surfaces": [{"topic": "rt/lowcmd", "status": "rejected"}],
            "ros2_topics_observed": ["/api/sport/request"],
            "source_trace": {"summary": {"confirmed": 1, "inferences": 0}},
        }

    monkeypatch.setattr(
        "g1_bobby_unitree_bridge.dds_introspection_cli.build_dds_introspection_report",
        fake_report,
    )

    exit_code = main(["--network-interface", "eth0", "--transport", "sdk_real"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["surfaces"][0]["topic"] == "rt/lowcmd"
    assert payload["source_trace"]["summary"]["confirmed"] == 1
