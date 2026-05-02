import json

from g1_bobby_unitree_bridge.export_bundle import main


def test_export_bundle_cli_collects_known_endpoints(monkeypatch, capsys) -> None:
    async def fake_bundle(api_url: str):
        assert api_url == "http://127.0.0.1:8010"
        return {"runtime": {"adapter": "mock"}, "sim_trace": {"classification": "state_only_runtime"}}

    monkeypatch.setattr("g1_bobby_unitree_bridge.export_bundle.build_export_bundle", fake_bundle)

    exit_code = main([])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["runtime"]["adapter"] == "mock"
    assert payload["sim_trace"]["classification"] == "state_only_runtime"
