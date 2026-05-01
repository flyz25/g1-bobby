from time import time

from fastapi.testclient import TestClient

from g1_bobby_api.app import create_app


def test_health_and_state_endpoints() -> None:
    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "online"}

        state = client.get("/state")
        assert state.status_code == 200
        body = state.json()
        assert body["type"] == "state"
        assert body["state"]["connected"] is True


def test_estop_and_reset_estop() -> None:
    with TestClient(create_app()) as client:
        estop = client.post("/estop")
        assert estop.status_code == 200
        assert estop.json()["state"]["estop_engaged"] is True

        reset = client.post("/reset-estop")
        assert reset.status_code == 200
        assert reset.json()["state"]["estop_engaged"] is False


def test_websocket_rejects_invalid_token() -> None:
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws/operator?token=bad") as websocket:
            event = websocket.receive_json()
            assert event["type"] == "reject"
            assert event["code"] == "auth_failed"


def test_websocket_rejects_movement_before_ready() -> None:
    with TestClient(create_app()) as client:
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


def test_websocket_accepts_safe_manual_movement() -> None:
    with TestClient(create_app()) as client:
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

