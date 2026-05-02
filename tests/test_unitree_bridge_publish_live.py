import json
import sys
from types import SimpleNamespace

from g1_bobby_unitree_bridge.publish_live import main


class _FakeRequest:
    def __init__(self) -> None:
        self.header = SimpleNamespace(identity=SimpleNamespace(api_id=None))
        self.parameter = None


class _FakePublisher:
    def __init__(self) -> None:
        self.messages = []

    def publish(self, message) -> None:
        self.messages.append(message)


class _FakeNode:
    def __init__(self) -> None:
        self.publisher = _FakePublisher()

    def create_publisher(self, message_class, topic: str, qos_depth: int):
        self.message_class = message_class
        self.topic = topic
        self.qos_depth = qos_depth
        return self.publisher

    def destroy_node(self) -> None:
        return None


def test_publish_live_cli_executes_ros2_real_set_mode(capsys, monkeypatch) -> None:
    fake_node = _FakeNode()
    fake_rclpy = SimpleNamespace(
        _ok=False,
        init=lambda args=None: setattr(fake_rclpy, "_ok", True),
        ok=lambda: getattr(fake_rclpy, "_ok"),
        shutdown=lambda: setattr(fake_rclpy, "_ok", False),
        create_node=lambda name: fake_node,
    )
    monkeypatch.setitem(sys.modules, "rclpy", fake_rclpy)
    monkeypatch.setitem(sys.modules, "unitree_api.msg", SimpleNamespace(Request=_FakeRequest))

    exit_code = main(
        [
            "--transport",
            "ros2_real",
            "--command-json",
            '{"type":"set_mode","seq":1,"timestamp":123.0,"payload":{"mode":"manual"}}',
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["transport"] == "ros2_real"
    assert payload["records"][0]["plan"]["transport"] == "ros2_real"
    assert payload["execution_results"][0]["status"] == "published"
    assert fake_node.topic == "/api/sport/request"
    assert fake_node.publisher.messages[0].header.identity.api_id == 7101


def test_publish_live_cli_executes_ros2_real_move_velocity(capsys, monkeypatch) -> None:
    fake_node = _FakeNode()
    fake_rclpy = SimpleNamespace(
        _ok=False,
        init=lambda args=None: setattr(fake_rclpy, "_ok", True),
        ok=lambda: getattr(fake_rclpy, "_ok"),
        shutdown=lambda: setattr(fake_rclpy, "_ok", False),
        create_node=lambda name: fake_node,
    )
    monkeypatch.setitem(sys.modules, "rclpy", fake_rclpy)
    monkeypatch.setitem(sys.modules, "unitree_api.msg", SimpleNamespace(Request=_FakeRequest))

    exit_code = main(
        [
            "--transport",
            "ros2_real",
            "--command-json",
            '{"type":"move_velocity","seq":3,"timestamp":123.0,"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.0,"duration_ms":100}}',
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_results"][0]["status"] == "published"
    assert fake_node.publisher.messages[0].header.identity.api_id == 7105
