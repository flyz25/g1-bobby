import json
import sys
from types import SimpleNamespace

from g1_bobby_unitree_bridge.publish_live import main


class _FakeRequest:
    def __init__(self) -> None:
        self.header = SimpleNamespace(identity=SimpleNamespace(api_id=None, id=None))
        self.parameter = None


class _FakeResponse:
    def __init__(self, request_id: int, api_id: int, code: int = 0, data: str = '{"ok": true}') -> None:
        self.header = SimpleNamespace(
            identity=SimpleNamespace(id=request_id, api_id=api_id),
            status=SimpleNamespace(code=code),
        )
        self.data = data


class _FakePublisher:
    def __init__(self, node: "_FakeNode") -> None:
        self.node = node
        self.messages = []

    def publish(self, message) -> None:
        self.messages.append(message)
        if self.node.response_callback is not None:
            self.node.response_callback(
                _FakeResponse(
                    request_id=message.header.identity.id,
                    api_id=message.header.identity.api_id,
                )
            )


class _FakeNode:
    def __init__(self) -> None:
        self.response_callback = None
        self.publisher = _FakePublisher(self)

    def create_publisher(self, message_class, topic: str, qos_depth: int):
        self.message_class = message_class
        self.topic = topic
        self.qos_depth = qos_depth
        return self.publisher

    def create_subscription(self, message_class, topic: str, callback, qos_depth: int):
        self.subscription_message_class = message_class
        self.subscription_topic = topic
        self.subscription_qos_depth = qos_depth
        self.response_callback = callback
        return object()

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
    monkeypatch.setitem(sys.modules, "unitree_api.msg", SimpleNamespace(Request=_FakeRequest, Response=_FakeResponse))

    exit_code = main(
        [
            "--transport",
            "ros2_real",
            "--response-timeout-s",
            "0.1",
            "--command-json",
            '{"type":"set_mode","seq":1,"timestamp":123.0,"payload":{"mode":"manual"}}',
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["transport"] == "ros2_real"
    assert payload["records"][0]["plan"]["transport"] == "ros2_real"
    assert payload["execution_results"][0]["status"] == "responded"
    assert payload["responses"][0]["api_id"] == 7101
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
    monkeypatch.setitem(sys.modules, "unitree_api.msg", SimpleNamespace(Request=_FakeRequest, Response=_FakeResponse))

    exit_code = main(
        [
            "--transport",
            "ros2_real",
            "--response-timeout-s",
            "0.1",
            "--command-json",
            '{"type":"move_velocity","seq":3,"timestamp":123.0,"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.0,"duration_ms":100}}',
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_results"][0]["status"] == "responded"
    assert payload["responses"][0]["api_id"] == 7105
    assert fake_node.publisher.messages[0].header.identity.api_id == 7105
