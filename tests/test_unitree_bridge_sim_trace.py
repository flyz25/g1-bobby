import json

from g1_bobby_unitree_bridge.sim_trace import main


def test_sim_trace_cli_classifies_state_only_runtime(monkeypatch, capsys) -> None:
    async def fake_report(**kwargs):
        return {
            "status": "blocked",
            "checks": {},
            "errors": [],
            "lowcmd_templates": [],
            "lowcmd_write_probe": {"status": "rejected", "topic": "rt/lowcmd", "write_result": False},
        }

    def fake_fetch_json(url: str):
        if url.endswith("/unitree/state"):
            return {"status": "receiving"}
        if url.endswith("/runtime"):
            return {"adapter": "unitree"}
        return None

    monkeypatch.setattr("g1_bobby_unitree_bridge.sim_trace.build_unitree_diagnostic_report", fake_report)
    monkeypatch.setattr("g1_bobby_unitree_bridge.sim_trace._fetch_json", fake_fetch_json)

    exit_code = main(
        [
            "--network-interface",
            "eth0",
            "--transport",
            "sdk_real",
            "--api-url",
            "http://127.0.0.1:8010",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["classification"] == "state_only_runtime"
    assert payload["api_unitree_state"]["status"] == "receiving"
