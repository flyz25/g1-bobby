import pytest
from types import SimpleNamespace

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError
from g1_bobby_contracts.commands import (
    CommandType,
    HeartbeatCommand,
    HeartbeatPayload,
    MoveVelocityCommand,
    MoveVelocityPayload,
    SetModeCommand,
    SetModePayload,
    StopCommand,
    StopPayload,
)
from g1_bobby_unitree_bridge.publisher_ros2 import (
    Ros2RealUnitreeCommandPublisher,
    build_ros2_publish_plan,
    resolve_ros2_binding,
)


def test_resolve_ros2_binding_maps_set_mode_to_sport_request() -> None:
    binding = resolve_ros2_binding(
        SetModeCommand(
            type=CommandType.SET_MODE,
            seq=1,
            timestamp=123.0,
            payload=SetModePayload(mode="manual"),
        )
    )

    assert binding is not None
    assert binding.topic == "/api/sport/request"
    assert binding.msg_type == "unitree_api/msg/Request"
    assert binding.binding_mode == "g1_loco_request"


def test_resolve_ros2_binding_maps_velocity_to_g1_loco_request() -> None:
    binding = resolve_ros2_binding(
        MoveVelocityCommand(
            type=CommandType.MOVE_VELOCITY,
            seq=3,
            timestamp=123.0,
            payload=MoveVelocityPayload(
                linear_x=0.1,
                linear_y=0.0,
                angular_z=0.0,
                duration_ms=100,
            ),
        )
    )

    assert binding is not None
    assert binding.topic == "/api/sport/request"
    assert binding.msg_type == "unitree_api/msg/Request"
    assert binding.binding_mode == "g1_loco_request"


def test_resolve_ros2_binding_maps_stop_to_g1_loco_request() -> None:
    binding = resolve_ros2_binding(
        StopCommand(
            type=CommandType.STOP,
            seq=4,
            timestamp=123.0,
            payload=StopPayload(reason="test_stop"),
        )
    )

    assert binding is not None
    assert binding.topic == "/api/sport/request"
    assert binding.msg_type == "unitree_api/msg/Request"


def test_resolve_ros2_binding_returns_none_for_heartbeat() -> None:
    binding = resolve_ros2_binding(
        HeartbeatCommand(
            type=CommandType.HEARTBEAT,
            seq=5,
            timestamp=123.0,
            payload=HeartbeatPayload(client_id="test-client"),
        )
    )

    assert binding is None


def test_build_ros2_publish_plan_maps_set_mode_payload() -> None:
    plan = build_ros2_publish_plan(
        SetModeCommand(
            type=CommandType.SET_MODE,
            seq=1,
            timestamp=123.0,
            payload=SetModePayload(mode="manual"),
        )
    )

    assert plan is not None
    assert plan.topic == "/api/sport/request"
    assert plan.payload == {"api_id": 7101, "parameter": {"data": 500}}


def test_build_ros2_publish_plan_maps_velocity_payload() -> None:
    plan = build_ros2_publish_plan(
        MoveVelocityCommand(
            type=CommandType.MOVE_VELOCITY,
            seq=3,
            timestamp=123.0,
            payload=MoveVelocityPayload(
                linear_x=0.1,
                linear_y=0.0,
                angular_z=0.2,
                duration_ms=100,
            ),
        )
    )

    assert plan is not None
    assert plan.topic == "/api/sport/request"
    assert plan.payload == {
        "api_id": 7105,
        "parameter": {"velocity": [0.1, 0.0, 0.2], "duration": 0.1},
    }


def test_build_ros2_publish_plan_returns_none_for_heartbeat() -> None:
    plan = build_ros2_publish_plan(
        HeartbeatCommand(
            type=CommandType.HEARTBEAT,
            seq=5,
            timestamp=123.0,
            payload=HeartbeatPayload(client_id="test-client"),
        )
    )

    assert plan is None


@pytest.mark.asyncio
async def test_ros2_real_publisher_publishes_move_velocity(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_node = _FakeNode()
    fake_rclpy = SimpleNamespace(
        _ok=False,
        init=lambda args=None: setattr(fake_rclpy, "_ok", True),
        ok=lambda: getattr(fake_rclpy, "_ok"),
        shutdown=lambda: setattr(fake_rclpy, "_ok", False),
        create_node=lambda name: fake_node,
    )
    monkeypatch.setitem(__import__("sys").modules, "rclpy", fake_rclpy)
    monkeypatch.setitem(__import__("sys").modules, "unitree_api.msg", SimpleNamespace(Request=_FakeRequest))
    publisher = Ros2RealUnitreeCommandPublisher()

    await publisher.connect()
    try:
        record = await publisher.publish(
            MoveVelocityCommand(
                type=CommandType.MOVE_VELOCITY,
                seq=3,
                timestamp=123.0,
                payload=MoveVelocityPayload(
                    linear_x=0.1,
                    linear_y=0.0,
                    angular_z=0.0,
                    duration_ms=100,
                ),
            )
        )
        assert record.plan.transport == "ros2_real"
        message = fake_node.publisher.messages[0]
        assert message.header.identity.api_id == 7105
        assert message.parameter == '{"velocity": [0.1, 0.0, 0.0], "duration": 0.1}'
    finally:
        await publisher.disconnect()


@pytest.mark.asyncio
async def test_ros2_real_publisher_rejects_unbound_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(__import__("sys").modules, "rclpy", object())
    publisher = Ros2RealUnitreeCommandPublisher()

    with pytest.raises(
        UnitreeTransportConfigurationError,
        match="no confirmed binding yet for command type: heartbeat",
    ):
        await publisher.publish(
            HeartbeatCommand(
                type=CommandType.HEARTBEAT,
                seq=5,
                timestamp=123.0,
                payload=HeartbeatPayload(client_id="test-client"),
            )
        )


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
        self.destroyed = False

    def create_publisher(self, message_class, topic: str, qos_depth: int):
        self.message_class = message_class
        self.topic = topic
        self.qos_depth = qos_depth
        return self.publisher

    def destroy_node(self) -> None:
        self.destroyed = True


@pytest.mark.asyncio
async def test_ros2_real_publisher_connects_and_publishes_set_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_node = _FakeNode()
    fake_rclpy = SimpleNamespace(
        _ok=False,
        init=lambda args=None: setattr(fake_rclpy, "_ok", True),
        ok=lambda: getattr(fake_rclpy, "_ok"),
        shutdown=lambda: setattr(fake_rclpy, "_ok", False),
        create_node=lambda name: fake_node,
    )
    monkeypatch.setitem(__import__("sys").modules, "rclpy", fake_rclpy)
    monkeypatch.setitem(__import__("sys").modules, "unitree_api.msg", SimpleNamespace(Request=_FakeRequest))
    publisher = Ros2RealUnitreeCommandPublisher()

    await publisher.connect()
    try:
        record = await publisher.publish(
            SetModeCommand(
                type=CommandType.SET_MODE,
                seq=1,
                timestamp=123.0,
                payload=SetModePayload(mode="manual"),
            )
        )
        assert record.plan.transport == "ros2_real"
        assert fake_node.topic == "/api/sport/request"
        assert fake_node.qos_depth == 10
        assert len(fake_node.publisher.messages) == 1
        message = fake_node.publisher.messages[0]
        assert message.header.identity.api_id == 7101
        assert message.parameter == '{"data": 500}'
        execution_plan = publisher.consume_last_execution_plan()
        assert execution_plan is not None
        assert execution_plan.transport == "ros2_real"
        assert execution_plan.target == "/api/sport/request"
        execution_result = publisher.consume_last_execution_result()
        assert execution_result is not None
        assert execution_result.status == "published"
    finally:
        await publisher.disconnect()
    assert fake_node.destroyed is True


@pytest.mark.asyncio
async def test_ros2_real_publisher_requires_request_module(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_rclpy = SimpleNamespace(
        _ok=False,
        init=lambda args=None: setattr(fake_rclpy, "_ok", True),
        ok=lambda: getattr(fake_rclpy, "_ok"),
        shutdown=lambda: setattr(fake_rclpy, "_ok", False),
        create_node=lambda name: _FakeNode(),
    )
    monkeypatch.setitem(__import__("sys").modules, "rclpy", fake_rclpy)
    __import__("sys").modules.pop("unitree_api.msg", None)
    publisher = Ros2RealUnitreeCommandPublisher()

    with pytest.raises(UnitreeTransportConfigurationError, match="unitree_api.msg"):
        await publisher.connect()


def test_build_ros2_publish_plan_rejects_unconfirmed_assist_mode() -> None:
    with pytest.raises(
        UnitreeTransportConfigurationError,
        match="no confirmed G1 loco FSM mapping for set_mode=assist",
    ):
        build_ros2_publish_plan(
            SetModeCommand(
                type=CommandType.SET_MODE,
                seq=1,
                timestamp=123.0,
                payload=SetModePayload(mode="assist"),
            )
        )
