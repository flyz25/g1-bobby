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
from g1_bobby_unitree_bridge.publisher_sdk import (
    SdkRealUnitreeCommandPublisher,
    build_sdk_publish_plan,
    resolve_sdk_binding,
)


def test_resolve_sdk_binding_maps_set_mode_to_sport_service() -> None:
    binding = resolve_sdk_binding(
        SetModeCommand(
            type=CommandType.SET_MODE,
            seq=1,
            timestamp=123.0,
            payload=SetModePayload(mode="manual"),
        )
    )

    assert binding is not None
    assert binding.transport_surface == "request_response"
    assert binding.binding_target == "SportClient/basic service request"
    assert binding.binding_mode == "sport_service"


def test_resolve_sdk_binding_maps_velocity_to_lowcmd() -> None:
    binding = resolve_sdk_binding(
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
    assert binding.transport_surface == "publish_subscribe"
    assert binding.binding_target == "rt/lowcmd (unitree_hg.msg.dds_.LowCmd_)"
    assert binding.binding_mode == "low_level_motor"


def test_resolve_sdk_binding_maps_stop_to_lowcmd() -> None:
    binding = resolve_sdk_binding(
        StopCommand(
            type=CommandType.STOP,
            seq=4,
            timestamp=123.0,
            payload=StopPayload(reason="test_stop"),
        )
    )

    assert binding is not None
    assert binding.binding_target == "rt/lowcmd (unitree_hg.msg.dds_.LowCmd_)"


def test_resolve_sdk_binding_returns_none_for_heartbeat() -> None:
    binding = resolve_sdk_binding(
        HeartbeatCommand(
            type=CommandType.HEARTBEAT,
            seq=5,
            timestamp=123.0,
            payload=HeartbeatPayload(client_id="test-client"),
        )
    )

    assert binding is None


def test_build_sdk_publish_plan_maps_set_mode_payload() -> None:
    plan = build_sdk_publish_plan(
        SetModeCommand(
            type=CommandType.SET_MODE,
            seq=1,
            timestamp=123.0,
            payload=SetModePayload(mode="manual"),
        )
    )

    assert plan is not None
    assert plan.binding_target == "SportClient/basic service request"
    assert plan.payload == {
        "client": "SportClient",
        "operation": "switch_mode",
        "parameter": {"mode": "manual"},
    }


def test_build_sdk_publish_plan_maps_velocity_payload() -> None:
    plan = build_sdk_publish_plan(
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
    assert plan.binding_target == "rt/lowcmd (unitree_hg.msg.dds_.LowCmd_)"
    assert plan.payload == {
        "mode_pr": 0,
        "mode_machine": "low_level",
        "velocity": {"linear_x": 0.1, "linear_y": 0.0, "angular_z": 0.2},
        "duration_ms": 100,
    }


def test_build_sdk_publish_plan_returns_none_for_heartbeat() -> None:
    plan = build_sdk_publish_plan(
        HeartbeatCommand(
            type=CommandType.HEARTBEAT,
            seq=5,
            timestamp=123.0,
            payload=HeartbeatPayload(client_id="test-client"),
        )
    )

    assert plan is None


@pytest.mark.asyncio
async def test_sdk_real_publisher_reports_bound_target_for_move_velocity() -> None:
    publisher = SdkRealUnitreeCommandPublisher(network_interface="eth0")

    with pytest.raises(
        UnitreeTransportConfigurationError,
        match=r"rt/lowcmd \(unitree_hg\.msg\.dds_\.LowCmd_\) \[publish_subscribe\].*duration_ms': 100",
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
async def test_sdk_real_publisher_reports_bound_target_for_set_mode() -> None:
    publisher = SdkRealUnitreeCommandPublisher(network_interface="eth0")

    with pytest.raises(
        UnitreeTransportConfigurationError,
        match=r"SportClient/basic service request \[request_response\].*switch_mode",
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
async def test_sdk_real_publisher_rejects_unbound_heartbeat() -> None:
    publisher = SdkRealUnitreeCommandPublisher(network_interface="eth0")

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
