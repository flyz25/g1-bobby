import json
from pathlib import Path
from time import time

from fastapi.testclient import TestClient

from g1_bobby_api.app import create_app
from g1_bobby_api.config import Settings


def unitree_snapshot(timestamp_s: float | None = None) -> dict[str, object]:
    return {
        "status": "receiving",
        "timestamp_s": time() if timestamp_s is None else timestamp_s,
        "dds": {
            "domain_id": 1,
            "interface": "lo",
            "robot": "g1",
            "topics": {
                "low_state": "rt/lowstate",
                "sport_mode_state": "rt/sportmodestate",
            },
        },
        "sample_counts": {"low_state": 1, "sport_mode_state": 1},
        "ages_s": {"low_state": 0.0, "sport_mode_state": 0.0},
        "low_state": {"motor_count": 35},
        "sport_mode_state": {"position": [0, 0, 1.2]},
    }


def build_settings(tmp_path: Path, **kwargs) -> Settings:
    return Settings(
        _env_file=None,
        unitree_state_cache_path=tmp_path / "unitree-state.json",
        unitree_command_plan_cache_path=tmp_path / "unitree-command-plans.jsonl",
        unitree_execution_plan_cache_path=tmp_path / "unitree-execution-plans.jsonl",
        unitree_execution_result_cache_path=tmp_path / "unitree-execution-results.jsonl",
        rejected_command_cache_path=tmp_path / "rejected-commands.jsonl",
        **kwargs,
    )


def test_health_and_state_endpoints(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        dashboard_redirect = client.get("/", follow_redirects=False)
        assert dashboard_redirect.status_code == 307
        assert dashboard_redirect.headers["location"] == "/dashboard"

        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200
        assert "G1 Bobby Operator" in dashboard.text

        asset = client.get("/assets/dashboard.js")
        assert asset.status_code == 200
        assert "connectSocket" in asset.text
        assert "executionPlanHistory" in asset.text
        assert "run-lowcmd-probe" in asset.text

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "online"}

        runtime = client.get("/runtime")
        assert runtime.status_code == 200
        runtime_body = runtime.json()
        assert runtime_body["adapter"] == "mock"
        assert runtime_body["active_operator_connected"] is False
        assert runtime_body["command_gate"]["max_commands_per_second"] == 20
        assert runtime_body["unitree_state"]["status"] == "not_available"
        assert runtime_body["unitree_execution_plan"]["available"] is False
        assert runtime_body["unitree_execution_result"]["available"] is False
        assert runtime_body["unitree_transport_capability"] is None
        assert runtime_body["rejected_command"]["available"] is False

        state = client.get("/state")
        assert state.status_code == 200
        body = state.json()
        assert body["type"] == "state"
        assert body["state"]["connected"] is True
        capability = client.get("/unitree/transport-capability")
        assert capability.status_code == 404

        lowcmd_templates = client.get("/unitree/lowcmd-templates")
        assert lowcmd_templates.status_code == 200
        assert lowcmd_templates.json()[0]["name"] == "neutral_probe"

        diagnostic = client.get("/unitree/diagnostic-report")
        assert diagnostic.status_code == 200
        diagnostic_body = diagnostic.json()
        assert diagnostic_body["lowcmd_templates"][0]["name"] == "neutral_probe"
        assert diagnostic_body["runtime_summary"]["adapter"] == "mock"
        assert "transport_capability" not in diagnostic_body


def test_estop_and_reset_estop(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        estop = client.post("/estop")
        assert estop.status_code == 200
        assert estop.json()["state"]["estop_engaged"] is True

        reset = client.post(
            "/reset-estop",
            headers={"X-Operator-Token": "dev-operator-token"},
        )
        assert reset.status_code == 200
        assert reset.json()["state"]["estop_engaged"] is False


def test_reset_estop_requires_operator_token(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        reset = client.post("/reset-estop")
        assert reset.status_code == 401
        assert reset.json()["detail"] == "invalid operator token"


def test_unitree_state_ingest_and_readback(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        missing = client.get("/unitree/state")
        assert missing.status_code == 404

        snapshot = unitree_snapshot()
        unauthorized = client.post("/unitree/state", json=snapshot)
        assert unauthorized.status_code == 401

        accepted = client.post(
            "/unitree/state",
            json=snapshot,
            headers={"X-Operator-Token": "dev-operator-token"},
        )
        assert accepted.status_code == 200
        assert accepted.json() == {
            "status": "accepted",
            "updates": 1,
            "snapshot_status": "receiving",
        }

        readback = client.get("/unitree/state")
        assert readback.status_code == 200
        assert readback.json()["low_state"]["motor_count"] == 35

        projected_state = client.get("/state")
        assert projected_state.status_code == 200
        assert projected_state.json()["state"]["pose_label"] == "unitree-g1 x=0.00 y=0.00 z=1.20"
        assert projected_state.json()["unitree_state"]["status"] == "receiving"
        assert projected_state.json()["unitree_state"]["source"] == "live"
        assert projected_state.json()["unitree_state"]["stale"] is False

        runtime = client.get("/runtime")
        assert runtime.json()["unitree_state"]["updates"] == 1
        assert runtime.json()["unitree_command_plan"]["available"] is False
        assert runtime.json()["unitree_command_plan"]["source"] is None
        assert runtime.json()["unitree_command_plan"]["stale"] is None
        assert runtime.json()["unitree_execution_plan"]["available"] is False
        assert runtime.json()["unitree_execution_result"]["available"] is False
        assert runtime.json()["rejected_command"]["available"] is False


def test_unitree_execution_plan_endpoint_missing_before_any_accept(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        response = client.get("/unitree/execution-plan")
        assert response.status_code == 404
        history = client.get("/unitree/execution-plans")
        assert history.status_code == 200
        assert history.json() == []


def test_unitree_execution_result_endpoint_missing_before_any_accept(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        response = client.get("/unitree/execution-result")
        assert response.status_code == 404
        history = client.get("/unitree/execution-results")
        assert history.status_code == 200
        assert history.json() == []


def test_unitree_transport_capability_endpoint_reports_current_unitree_transport(tmp_path: Path) -> None:
    settings = build_settings(
        tmp_path,
        robot_adapter="unitree",
        unitree_network_interface="eth0",
        unitree_sdk_module="unitree_sdk_for_test",
        unitree_enable_motor_commands=True,
        unitree_command_transport="dry_run",
    )
    import sys
    from types import SimpleNamespace

    sys.modules["unitree_sdk_for_test"] = SimpleNamespace()
    try:
        with TestClient(create_app(settings)) as client:
            response = client.get("/unitree/transport-capability")
            assert response.status_code == 200
            payload = response.json()
            assert payload["transport"] == "dry_run"
            assert payload["configured"] is True
            assert payload["execution_enabled"] is True
            assert payload["binding_implemented"] is True
            assert payload["ready"] is True

            runtime = client.get("/runtime")
            assert runtime.status_code == 200
            assert runtime.json()["unitree_transport_capability"]["transport"] == "dry_run"

            diagnostic = client.get("/unitree/diagnostic-report")
            assert diagnostic.status_code == 200
            assert diagnostic.json()["transport_capability"]["transport"] == "dry_run"
    finally:
        sys.modules.pop("unitree_sdk_for_test", None)


def test_unitree_diagnostic_report_can_include_lowcmd_probe(tmp_path: Path, monkeypatch) -> None:
    async def fake_report(**kwargs):
        assert kwargs["probe_lowcmd_write"] is True
        return {
            "status": "blocked",
            "checks": {"dds_interface": "eth0"},
            "errors": [],
            "lowcmd_templates": [{"name": "neutral_probe", "defaults": {"topic": "rt/lowcmd"}}],
            "lowcmd_write_probe": {"status": "rejected", "topic": "rt/lowcmd", "write_result": False},
        }

    monkeypatch.setattr("g1_bobby_api.app.build_unitree_diagnostic_report", fake_report)

    with TestClient(create_app(build_settings(tmp_path))) as client:
        response = client.get("/unitree/diagnostic-report?probe_lowcmd_write=true")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "blocked"
        assert payload["lowcmd_write_probe"]["status"] == "rejected"


def test_websocket_rejects_invalid_token(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        with client.websocket_connect("/ws/operator?token=bad") as websocket:
            event = websocket.receive_json()
            assert event["type"] == "reject"
            assert event["code"] == "auth_failed"


def test_audit_websocket_rejects_invalid_token(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        with client.websocket_connect("/ws/operator/audit?token=bad") as websocket:
            event = websocket.receive_json()
            assert event["type"] == "reject"
            assert event["code"] == "auth_failed"


def test_rejected_command_endpoint_missing_before_any_reject(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        response = client.get("/operator/rejection")
        assert response.status_code == 404
        history = client.get("/operator/rejections")
        assert history.status_code == 200
        assert history.json() == []


def test_unitree_state_is_restored_after_app_restart(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        accepted = client.post(
            "/unitree/state",
            json=unitree_snapshot(),
            headers={"X-Operator-Token": "dev-operator-token"},
        )
        assert accepted.status_code == 200

    with TestClient(create_app(settings)) as restarted_client:
        restored_runtime = restarted_client.get("/runtime")
        assert restored_runtime.json()["unitree_state"]["status"] == "receiving"
        assert restored_runtime.json()["unitree_state"]["updates"] == 1
        assert restored_runtime.json()["unitree_state"]["source"] == "restored"
        assert restored_runtime.json()["unitree_state"]["stale"] is False

        restored_state = restarted_client.get("/state")
        assert restored_state.json()["state"]["pose_label"] == "unitree-g1 x=0.00 y=0.00 z=1.20"
        assert restored_state.json()["unitree_state"]["status"] == "receiving"
        assert restored_state.json()["unitree_state"]["source"] == "restored"


def test_restored_unitree_state_can_be_marked_stale(tmp_path: Path) -> None:
    settings = build_settings(
        tmp_path,
        unitree_state_ttl_s=0.01,
    )
    with TestClient(create_app(settings)) as client:
        accepted = client.post(
            "/unitree/state",
            json=unitree_snapshot(timestamp_s=time() - 5.0),
            headers={"X-Operator-Token": "dev-operator-token"},
        )
        assert accepted.status_code == 200

    with TestClient(create_app(settings)) as restarted_client:
        restored_runtime = restarted_client.get("/runtime")
        assert restored_runtime.json()["unitree_state"]["source"] == "restored"
        assert restored_runtime.json()["unitree_state"]["stale"] is True

        restored_state = restarted_client.get("/state")
        assert restored_state.json()["state"]["connected"] is False


def test_websocket_state_and_telemetry_include_unitree_snapshot(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, telemetry_interval_s=0.01)
    with TestClient(create_app(settings)) as client:
        accepted = client.post(
            "/unitree/state",
            json=unitree_snapshot(),
            headers={"X-Operator-Token": "dev-operator-token"},
        )
        assert accepted.status_code == 200

        with client.websocket_connect("/ws/operator?token=dev-operator-token") as websocket:
            state_event = websocket.receive_json()
            assert state_event["type"] == "state"
            assert state_event["state"]["pose_label"] == "unitree-g1 x=0.00 y=0.00 z=1.20"
            assert state_event["unitree_state"]["status"] == "receiving"
            assert state_event["unitree_state"]["source"] == "live"
            assert state_event["unitree_state"]["stale"] is False
            assert state_event["unitree_state"]["low_state"]["motor_count"] == 35

            telemetry_event = websocket.receive_json()
            assert telemetry_event["type"] == "telemetry"
            assert telemetry_event["state"]["pose_label"] == "unitree-g1 x=0.00 y=0.00 z=1.20"
            assert telemetry_event["unitree_state"]["source"] == "live"
            assert telemetry_event["unitree_state"]["sample_counts"]["low_state"] == 1
            assert telemetry_event["unitree_state"]["sport_mode_state"]["position"][2] == 1.2


def test_websocket_rejects_movement_before_ready(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as websocket:
            assert websocket.receive_json()["type"] == "state"
            websocket.send_json(
                {
                    "type": "move_velocity",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {
                        "linear_x": 0.1,
                        "linear_y": 0.0,
                        "angular_z": 0.0,
                        "duration_ms": 100,
                    },
                }
            )
            event = websocket.receive_json()
            assert event["type"] == "reject"
            assert event["seq"] == 1
            assert event["code"] == "safety_rejected"


def test_websocket_accepts_safe_manual_movement(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as websocket:
            assert websocket.receive_json()["type"] == "state"

            websocket.send_json(
                {
                    "type": "heartbeat",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"client_id": "quest-dev"},
                }
            )
            heartbeat_ack = websocket.receive_json()
            assert heartbeat_ack["type"] == "ack"
            assert heartbeat_ack["unitree_command_plan"]["source"] == "live"
            assert heartbeat_ack["unitree_command_plan"]["stale"] is False
            assert heartbeat_ack["unitree_command_plan"]["plan"]["action"] == "bridge.keepalive"
            assert heartbeat_ack["unitree_execution_plan"] is None

            websocket.send_json(
                {
                    "type": "set_mode",
                    "seq": 2,
                    "timestamp": time(),
                    "payload": {"mode": "manual"},
                }
            )
            mode_ack = websocket.receive_json()
            assert mode_ack["type"] == "ack"
            assert mode_ack["unitree_command_plan"]["plan"]["action"] == "bridge.set_mode"
            assert mode_ack["unitree_execution_plan"] is None

            websocket.send_json(
                {
                    "type": "move_velocity",
                    "seq": 3,
                    "timestamp": time(),
                    "payload": {
                        "linear_x": 0.1,
                        "linear_y": 0.0,
                        "angular_z": 0.0,
                        "duration_ms": 100,
                    },
                }
            )
            event = websocket.receive_json()
            assert event["type"] == "ack"
            assert event["seq"] == 3
            assert event["unitree_command_plan"]["plan"]["action"] == "motion.velocity"
            assert event["unitree_command_plan"]["plan"]["unitree_target"] == "base_velocity"
            assert event["unitree_command_plan"]["source"] == "live"
            assert event["unitree_command_plan"]["stale"] is False

        plan = client.get("/unitree/command-plan")
        assert plan.status_code == 200
        assert plan.json()["event_id"] == 3
        assert plan.json()["source"] == "live"
        assert plan.json()["stale"] is False
        assert plan.json()["plan"]["action"] == "motion.velocity"
        assert plan.json()["plan"]["payload"]["angular_z"] == 0.0

        runtime = client.get("/runtime")
        assert runtime.json()["unitree_command_plan"]["available"] is True
        assert runtime.json()["unitree_command_plan"]["plans"] == 3
        assert runtime.json()["unitree_command_plan"]["retained"] == 3
        assert runtime.json()["unitree_command_plan"]["history_size"] == 10
        assert runtime.json()["unitree_command_plan"]["source"] == "live"
        assert runtime.json()["unitree_command_plan"]["stale"] is False

        history = client.get("/unitree/command-plans")
        assert history.status_code == 200
        assert [record["event_id"] for record in history.json()] == [1, 2, 3]
        assert [record["plan"]["action"] for record in history.json()] == [
            "bridge.keepalive",
            "bridge.set_mode",
            "motion.velocity",
        ]


def test_plan_stub_execution_plan_endpoints_and_audit_stream(tmp_path: Path) -> None:
    import sys
    from types import SimpleNamespace

    settings = build_settings(
        tmp_path,
        robot_adapter="unitree",
        unitree_network_interface="eth0",
        unitree_sdk_module="unitree_sdk_for_test",
        unitree_enable_motor_commands=True,
        unitree_command_transport="ros2_plan_stub",
    )
    sys.modules["unitree_sdk_for_test"] = SimpleNamespace()

    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as operator:
            assert operator.receive_json()["type"] == "state"
            operator.send_json(
                {
                    "type": "set_mode",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"mode": "manual"},
                }
            )
            mode_ack = operator.receive_json()
            assert mode_ack["unitree_execution_plan"]["execution_plan"]["transport"] == "ros2_plan_stub"
            assert mode_ack["unitree_execution_plan"]["execution_plan"]["target"] == "/api/sport/request"
            assert mode_ack["unitree_execution_result"]["execution_result"]["status"] == "stub_emitted"

            with client.websocket_connect("/ws/operator/audit?token=dev-operator-token") as audit:
                first = audit.receive_json()
                second = audit.receive_json()
                third = audit.receive_json()
                assert {first["type"], second["type"], third["type"]} == {
                    "command_plan",
                    "execution_plan",
                    "execution_result",
                }
                execution_event = first if first["type"] == "execution_plan" else second
                if execution_event["type"] != "execution_plan":
                    execution_event = third
                assert execution_event["unitree_execution_plan"]["execution_plan"]["transport"] == "ros2_plan_stub"
                assert execution_event["unitree_execution_plan"]["execution_plan"]["target"] == "/api/sport/request"
                result_event = first if first["type"] == "execution_result" else second
                if result_event["type"] != "execution_result":
                    result_event = third
                assert result_event["unitree_execution_result"]["execution_result"]["status"] == "stub_emitted"

        latest = client.get("/unitree/execution-plan")
        assert latest.status_code == 200
        assert latest.json()["execution_plan"]["transport"] == "ros2_plan_stub"
        assert latest.json()["execution_plan"]["target"] == "/api/sport/request"

        history = client.get("/unitree/execution-plans")
        assert history.status_code == 200
        assert len(history.json()) == 1
        assert history.json()[0]["execution_plan"]["command_type"] == "set_mode"

        result = client.get("/unitree/execution-result")
        assert result.status_code == 200
        assert result.json()["execution_result"]["status"] == "stub_emitted"

        result_history = client.get("/unitree/execution-results")
        assert result_history.status_code == 200
        assert len(result_history.json()) == 1
        assert result_history.json()[0]["execution_result"]["transport"] == "ros2_plan_stub"

        runtime = client.get("/runtime")
        assert runtime.json()["unitree_execution_plan"]["available"] is True
        assert runtime.json()["unitree_execution_plan"]["plans"] == 1
        assert runtime.json()["unitree_execution_plan"]["source"] == "live"
        assert runtime.json()["unitree_execution_result"]["available"] is True
        assert runtime.json()["unitree_execution_result"]["results"] == 1


def test_execution_failure_records_blocked_execution_result(tmp_path: Path) -> None:
    import sys
    from types import SimpleNamespace

    settings = build_settings(
        tmp_path,
        robot_adapter="unitree",
        unitree_network_interface="eth0",
        unitree_sdk_module="unitree_sdk_for_test",
        unitree_enable_motor_commands=True,
        unitree_command_transport="disabled",
    )
    sys.modules["unitree_sdk_for_test"] = SimpleNamespace()

    try:
        with TestClient(create_app(settings)) as client:
            with client.websocket_connect("/ws/operator?token=dev-operator-token") as operator:
                assert operator.receive_json()["type"] == "state"
                operator.send_json(
                    {
                        "type": "set_mode",
                        "seq": 1,
                        "timestamp": time(),
                        "payload": {"mode": "manual"},
                    }
                )
                reject = operator.receive_json()
                assert reject["type"] == "reject"
                assert reject["code"] == "execution_failed"
                assert reject["unitree_execution_result"]["execution_result"]["status"] == "blocked"
                assert reject["unitree_execution_result"]["execution_result"]["transport"] == "disabled"

                with client.websocket_connect("/ws/operator/audit?token=dev-operator-token") as audit:
                    first = audit.receive_json()
                    second = audit.receive_json()
                    assert {first["type"], second["type"]} == {"execution_result", "rejected_command"}
                    execution_result_event = first if first["type"] == "execution_result" else second
                    assert execution_result_event["unitree_execution_result"]["execution_result"]["status"] == "blocked"
                    assert execution_result_event["unitree_execution_result"]["execution_result"]["transport"] == "disabled"
                    rejected_event = first if first["type"] == "rejected_command" else second
                    assert (
                        rejected_event["rejected_command"]["rejection"]["unitree_execution_result"]["execution_result"]["status"]
                        == "blocked"
                    )

            latest = client.get("/unitree/execution-result")
            assert latest.status_code == 200
            assert latest.json()["execution_result"]["status"] == "blocked"
            assert latest.json()["execution_result"]["transport"] == "disabled"
            assert latest.json()["execution_result"]["command_type"] == "set_mode"

            runtime = client.get("/runtime")
            assert runtime.status_code == 200
            assert runtime.json()["unitree_execution_result"]["available"] is True
            assert runtime.json()["unitree_execution_result"]["results"] == 1
            assert runtime.json()["rejected_command"]["records"] == 1
    finally:
        sys.modules.pop("unitree_sdk_for_test", None)


def test_unitree_command_plan_missing_before_any_accept(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        response = client.get("/unitree/command-plan")
        assert response.status_code == 404
        history = client.get("/unitree/command-plans")
        assert history.status_code == 200
        assert history.json() == []


def test_unitree_command_plan_history_is_trimmed(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, unitree_command_plan_history_size=2)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as websocket:
            assert websocket.receive_json()["type"] == "state"

            websocket.send_json(
                {
                    "type": "heartbeat",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"client_id": "quest-dev"},
                }
            )
            assert websocket.receive_json()["type"] == "ack"

            websocket.send_json(
                {
                    "type": "set_mode",
                    "seq": 2,
                    "timestamp": time(),
                    "payload": {"mode": "manual"},
                }
            )
            assert websocket.receive_json()["type"] == "ack"

            websocket.send_json(
                {
                    "type": "move_velocity",
                    "seq": 3,
                    "timestamp": time(),
                    "payload": {
                        "linear_x": 0.1,
                        "linear_y": 0.0,
                        "angular_z": 0.0,
                        "duration_ms": 100,
                    },
                }
            )
            assert websocket.receive_json()["type"] == "ack"

        history = client.get("/unitree/command-plans")
        assert history.status_code == 200
        assert [record["plan"]["seq"] for record in history.json()] == [2, 3]
        assert all(record["source"] == "live" for record in history.json())

        runtime = client.get("/runtime")
        assert runtime.json()["unitree_command_plan"]["plans"] == 3
        assert runtime.json()["unitree_command_plan"]["retained"] == 2
        assert runtime.json()["unitree_command_plan"]["history_size"] == 2
        assert runtime.json()["unitree_command_plan"]["source"] == "live"
        assert runtime.json()["unitree_command_plan"]["stale"] is False


def test_unitree_command_plan_history_is_restored_after_app_restart(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, unitree_command_plan_history_size=2)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as websocket:
            assert websocket.receive_json()["type"] == "state"

            for seq, command_type, payload in (
                (1, "heartbeat", {"client_id": "quest-dev"}),
                (2, "set_mode", {"mode": "manual"}),
                (
                    3,
                    "move_velocity",
                    {
                        "linear_x": 0.1,
                        "linear_y": 0.0,
                        "angular_z": 0.0,
                        "duration_ms": 100,
                    },
                ),
            ):
                websocket.send_json(
                    {
                        "type": command_type,
                        "seq": seq,
                        "timestamp": time(),
                        "payload": payload,
                    }
                )
                assert websocket.receive_json()["type"] == "ack"

    with TestClient(create_app(settings)) as restarted_client:
        plan = restarted_client.get("/unitree/command-plan")
        assert plan.status_code == 200
        assert plan.json()["plan"]["seq"] == 3
        assert plan.json()["source"] == "restored"
        assert plan.json()["stale"] is False

        history = restarted_client.get("/unitree/command-plans")
        assert history.status_code == 200
        assert [item["plan"]["seq"] for item in history.json()] == [2, 3]
        assert all(item["source"] == "restored" for item in history.json())

        runtime = restarted_client.get("/runtime")
        assert runtime.json()["unitree_command_plan"]["available"] is True
        assert runtime.json()["unitree_command_plan"]["plans"] == 2
        assert runtime.json()["unitree_command_plan"]["retained"] == 2
        assert runtime.json()["unitree_command_plan"]["history_size"] == 2
        assert runtime.json()["unitree_command_plan"]["last_recorded_at"] is not None
        assert runtime.json()["unitree_command_plan"]["source"] == "restored"
        assert runtime.json()["unitree_command_plan"]["stale"] is False


def test_audit_websocket_replays_history_and_streams_live_updates(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, unitree_command_plan_history_size=2)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as operator:
            assert operator.receive_json()["type"] == "state"
            operator.send_json(
                {
                    "type": "heartbeat",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"client_id": "quest-dev"},
                }
            )
            operator.receive_json()
            operator.send_json(
                {
                    "type": "set_mode",
                    "seq": 2,
                    "timestamp": time(),
                    "payload": {"mode": "manual"},
                }
            )
            operator.receive_json()

            with client.websocket_connect("/ws/operator/audit?token=dev-operator-token") as audit:
                replay = [audit.receive_json(), audit.receive_json()]
                command_plan_events = [item for item in replay if item["type"] == "command_plan"]
                assert len(command_plan_events) == 2
                assert [item["unitree_command_plan"]["plan"]["seq"] for item in command_plan_events] == [1, 2]
                assert all(item["unitree_command_plan"]["source"] == "live" for item in command_plan_events)

                operator.send_json(
                    {
                        "type": "move_velocity",
                        "seq": 3,
                        "timestamp": time(),
                        "payload": {
                            "linear_x": 0.1,
                            "linear_y": 0.0,
                            "angular_z": 0.0,
                            "duration_ms": 100,
                        },
                    }
                )
                operator.receive_json()
                live = audit.receive_json()
                assert live["type"] == "command_plan"
                assert live["unitree_command_plan"]["plan"]["seq"] == 3
                assert live["unitree_command_plan"]["plan"]["action"] == "motion.velocity"
                assert live["unitree_command_plan"]["source"] == "live"
                assert live["unitree_command_plan"]["stale"] is False


def test_rejected_command_endpoints_and_audit_stream(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, rejected_command_history_size=2)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as operator:
            assert operator.receive_json()["type"] == "state"
            operator.send_json(
                {
                    "type": "heartbeat",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"client_id": "quest-dev"},
                }
            )
            assert operator.receive_json()["type"] == "ack"
            operator.send_json(
                {
                    "type": "set_mode",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"mode": "manual"},
                }
            )
            reject = operator.receive_json()
            assert reject["type"] == "reject"
            assert reject["code"] == "replayed_command"

            latest = client.get("/operator/rejection")
            assert latest.status_code == 200
            assert latest.json()["rejection"]["code"] == "replayed_command"
            assert latest.json()["command_type"] == "set_mode"
            assert latest.json()["source"] == "live"

            history = client.get("/operator/rejections")
            assert history.status_code == 200
            assert history.json()[0]["rejection"]["seq"] == 1

            runtime = client.get("/runtime")
            assert runtime.json()["rejected_command"]["available"] is True
            assert runtime.json()["rejected_command"]["records"] == 1
            assert runtime.json()["rejected_command"]["source"] == "live"

            with client.websocket_connect("/ws/operator/audit?token=dev-operator-token") as audit:
                first = audit.receive_json()
                second = audit.receive_json()
                assert {first["type"], second["type"]} == {"command_plan", "rejected_command"}
                rejected_event = first if first["type"] == "rejected_command" else second
                assert rejected_event["rejected_command"]["rejection"]["code"] == "replayed_command"
                assert rejected_event["rejected_command"]["command_type"] == "set_mode"

                operator.send_json(
                    {
                        "type": "heartbeat",
                        "seq": 1,
                        "timestamp": time(),
                        "payload": {"client_id": "quest-dev"},
                    }
                )
                live = audit.receive_json()
                assert live["type"] == "rejected_command"
                assert live["rejected_command"]["rejection"]["code"] == "replayed_command"


def test_rejected_command_history_is_restored_after_restart(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, rejected_command_history_size=2)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as websocket:
            assert websocket.receive_json()["type"] == "state"
            websocket.send_json(
                {
                    "type": "heartbeat",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"client_id": "quest-dev"},
                }
            )
            assert websocket.receive_json()["type"] == "ack"
            websocket.send_json(
                {
                    "type": "set_mode",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"mode": "manual"},
                }
            )
            assert websocket.receive_json()["type"] == "reject"

    with TestClient(create_app(settings)) as restarted_client:
        latest = restarted_client.get("/operator/rejection")
        assert latest.status_code == 200
        assert latest.json()["source"] == "restored"
        assert latest.json()["stale"] is False
        history = restarted_client.get("/operator/rejections")
        assert history.status_code == 200
        assert history.json()[0]["source"] == "restored"
        runtime = restarted_client.get("/runtime")
        assert runtime.json()["rejected_command"]["source"] == "restored"


def test_audit_websocket_after_id_replays_only_newer_events(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, unitree_command_plan_history_size=3, rejected_command_history_size=3)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as operator:
            assert operator.receive_json()["type"] == "state"
            operator.send_json(
                {
                    "type": "heartbeat",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"client_id": "quest-dev"},
                }
            )
            operator.receive_json()
            operator.send_json(
                {
                    "type": "set_mode",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"mode": "manual"},
                }
            )
            operator.receive_json()

        with client.websocket_connect("/ws/operator/audit?token=dev-operator-token&after_id=1") as audit:
            event = audit.receive_json()
            assert event["type"] in {"rejected_command", "command_plan"}
            if event["type"] == "rejected_command":
                assert event["rejected_command"]["rejection"]["code"] == "replayed_command"
            else:
                assert event["unitree_command_plan"]["plan"]["seq"] == 1


def test_restored_unitree_command_plan_can_be_marked_stale(tmp_path: Path) -> None:
    settings = build_settings(
        tmp_path,
        unitree_command_plan_history_size=2,
        unitree_command_plan_ttl_s=0.01,
    )
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as websocket:
            assert websocket.receive_json()["type"] == "state"
            websocket.send_json(
                {
                    "type": "heartbeat",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"client_id": "quest-dev"},
                }
            )
            assert websocket.receive_json()["type"] == "ack"

    payload = settings.unitree_command_plan_cache_path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(payload[-1])
    entry["recorded_at"] -= 5.0
    settings.unitree_command_plan_cache_path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    with TestClient(create_app(settings)) as restarted_client:
        plan = restarted_client.get("/unitree/command-plan")
        assert plan.status_code == 200
        assert plan.json()["source"] == "restored"
        assert plan.json()["stale"] is True

        runtime = restarted_client.get("/runtime")
        assert runtime.json()["unitree_command_plan"]["source"] == "restored"
        assert runtime.json()["unitree_command_plan"]["stale"] is True


def test_websocket_rejects_replayed_sequence(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as websocket:
            assert websocket.receive_json()["type"] == "state"

            websocket.send_json(
                {
                    "type": "heartbeat",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"client_id": "quest-dev"},
                }
            )
            assert websocket.receive_json()["type"] == "ack"

            websocket.send_json(
                {
                    "type": "set_mode",
                    "seq": 1,
                    "timestamp": time(),
                    "payload": {"mode": "manual"},
                }
            )
            event = websocket.receive_json()
            assert event["type"] == "reject"
            assert event["seq"] == 1
            assert event["code"] == "replayed_command"


def test_websocket_rejects_stale_command_timestamp(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path, command_max_age_s=0.1))) as client:
        with client.websocket_connect("/ws/operator?token=dev-operator-token") as websocket:
            assert websocket.receive_json()["type"] == "state"
            websocket.send_json(
                {
                    "type": "heartbeat",
                    "seq": 1,
                    "timestamp": time() - 1.0,
                    "payload": {"client_id": "quest-dev"},
                }
            )
            event = websocket.receive_json()
            assert event["type"] == "reject"
            assert event["seq"] == 1
            assert event["code"] == "stale_command"
