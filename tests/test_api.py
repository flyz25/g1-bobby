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
        **kwargs,
    )


def test_health_and_state_endpoints(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
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

        state = client.get("/state")
        assert state.status_code == 200
        body = state.json()
        assert body["type"] == "state"
        assert body["state"]["connected"] is True


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


def test_websocket_rejects_invalid_token(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        with client.websocket_connect("/ws/operator?token=bad") as websocket:
            event = websocket.receive_json()
            assert event["type"] == "reject"
            assert event["code"] == "auth_failed"


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
            event = websocket.receive_json()
            assert event["type"] == "ack"
            assert event["seq"] == 3

        plan = client.get("/unitree/command-plan")
        assert plan.status_code == 200
        assert plan.json()["action"] == "motion.velocity"
        assert plan.json()["payload"]["angular_z"] == 0.0

        runtime = client.get("/runtime")
        assert runtime.json()["unitree_command_plan"]["available"] is True
        assert runtime.json()["unitree_command_plan"]["plans"] == 3


def test_unitree_command_plan_missing_before_any_accept(tmp_path: Path) -> None:
    with TestClient(create_app(build_settings(tmp_path))) as client:
        response = client.get("/unitree/command-plan")
        assert response.status_code == 404


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
