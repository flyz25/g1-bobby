import pytest

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
    assert binding.binding_mode == "sport_request"


def test_resolve_ros2_binding_maps_velocity_to_lowcmd() -> None:
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
    assert binding.topic == "/lowcmd"
    assert binding.msg_type == "LowCmd"
    assert binding.binding_mode == "low_level_motor"


def test_resolve_ros2_binding_maps_stop_to_lowcmd() -> None:
    binding = resolve_ros2_binding(
        StopCommand(
            type=CommandType.STOP,
            seq=4,
            timestamp=123.0,
            payload=StopPayload(reason="test_stop"),
        )
    )

    assert binding is not None
    assert binding.topic == "/lowcmd"
    assert binding.msg_type == "LowCmd"


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
    assert plan.payload == {"api_id": "switch_mode", "parameter": {"mode": "manual"}}


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
    assert plan.topic == "/lowcmd"
    assert plan.payload == {
        "mode": "velocity",
        "velocity": {"linear_x": 0.1, "linear_y": 0.0, "angular_z": 0.2},
        "duration_ms": 100,
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
async def test_ros2_real_publisher_reports_bound_topic_for_move_velocity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(__import__("sys").modules, "rclpy", object())
    publisher = Ros2RealUnitreeCommandPublisher()

    with pytest.raises(
        UnitreeTransportConfigurationError,
        match=r"/lowcmd \(LowCmd\).*duration_ms': 100",
    ):
        await publisher.publish(
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


@pytest.mark.asyncio
async def test_ros2_real_publisher_reports_bound_topic_for_set_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(__import__("sys").modules, "rclpy", object())
    publisher = Ros2RealUnitreeCommandPublisher()

    with pytest.raises(
        UnitreeTransportConfigurationError,
        match=r"/api/sport/request \(unitree_api/msg/Request\).*switch_mode",
    ):
        await publisher.publish(
            SetModeCommand(
                type=CommandType.SET_MODE,
                seq=1,
                timestamp=123.0,
                payload=SetModePayload(mode="manual"),
            )
        )


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
