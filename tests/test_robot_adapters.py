from types import SimpleNamespace
from time import time

import pytest

from g1_bobby_contracts.commands import (
    CommandType,
    SetModeCommand,
    SetModePayload,
    StopCommand,
    StopPayload,
)
from g1_bobby_contracts.state import ControlMode
from g1_bobby_adapters import (
    DryRunUnitreeCommandPublisher,
    MockRobotAdapter,
    UnitreeAdapter,
    UnitreeAdapterConfig,
    UnitreeAdapterConfigurationError,
    describe_unitree_transport_capability,
)
from g1_bobby_unitree_bridge.publisher_plan_stub import PlanStubUnitreeCommandPublisher


async def test_mock_stop_returns_robot_to_idle() -> None:
    adapter = MockRobotAdapter()
    await adapter.connect()
    await adapter.execute(
        SetModeCommand(
            type=CommandType.SET_MODE,
            seq=1,
            timestamp=time(),
            payload=SetModePayload(mode="manual"),
        )
    )

    manual_state = await adapter.get_state()
    assert manual_state.mode == ControlMode.MANUAL

    await adapter.execute(
        StopCommand(
            type=CommandType.STOP,
            seq=2,
            timestamp=time(),
            payload=StopPayload(reason="test_stop"),
        )
    )

    stopped_state = await adapter.get_state()
    assert stopped_state.mode == ControlMode.IDLE


async def test_unitree_dry_run_transport_publishes_without_actuation(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    publisher = DryRunUnitreeCommandPublisher()
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="unitree_sdk_for_test",
            enable_motor_commands=True,
            command_transport="dry_run",
        ),
        publisher=publisher,
    )
    await adapter.connect()
    try:
        await adapter.execute(
            SetModeCommand(
                type=CommandType.SET_MODE,
                seq=1,
                timestamp=time(),
                payload=SetModePayload(mode="manual"),
            )
        )
        await adapter.execute(
            StopCommand(
                type=CommandType.STOP,
                seq=2,
                timestamp=time(),
                payload=StopPayload(reason="test_stop"),
            )
        )

        records = publisher.published_records()
        assert [record.plan.action for record in records] == ["bridge.set_mode", "motion.stop"]
        state = await adapter.get_state()
        assert state.mode == ControlMode.IDLE
    finally:
        await adapter.disconnect()


async def test_unitree_ros2_stub_transport_publishes_without_actuation(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="unitree_sdk_for_test",
            enable_motor_commands=True,
            command_transport="ros2_stub",
        ),
    )
    await adapter.connect()
    try:
        await adapter.execute(
            SetModeCommand(
                type=CommandType.SET_MODE,
                seq=1,
                timestamp=time(),
                payload=SetModePayload(mode="manual"),
            )
        )
        state = await adapter.get_state()
        assert state.connected is True
        assert state.mode == ControlMode.MANUAL
        assert state.pose_label == "unitree-ros2_stub"
    finally:
        await adapter.disconnect()


async def test_unitree_ros2_plan_stub_transport_executes_publish_plan(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    publisher = PlanStubUnitreeCommandPublisher(transport="ros2_plan_stub")
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="unitree_sdk_for_test",
            enable_motor_commands=True,
            command_transport="ros2_plan_stub",
        ),
        publisher=publisher,
    )
    await adapter.connect()
    try:
        await adapter.execute(
            StopCommand(
                type=CommandType.STOP,
                seq=2,
                timestamp=time(),
                payload=StopPayload(reason="test_stop"),
            )
        )
        emitted = publisher.emitted_plans()
        assert emitted[0].target == "/api/sport/request"
        assert emitted[0].payload["api_id"] == 7105
        assert emitted[0].payload["parameter"]["velocity"] == [0.0, 0.0, 0.0]
    finally:
        await adapter.disconnect()


async def test_unitree_sdk_plan_stub_transport_executes_publish_plan(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    publisher = PlanStubUnitreeCommandPublisher(transport="sdk_plan_stub")
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="unitree_sdk_for_test",
            enable_motor_commands=True,
            command_transport="sdk_plan_stub",
        ),
        publisher=publisher,
    )
    await adapter.connect()
    try:
        await adapter.execute(
            SetModeCommand(
                type=CommandType.SET_MODE,
                seq=1,
                timestamp=time(),
                payload=SetModePayload(mode="manual"),
            )
        )
        emitted = publisher.emitted_plans()
        assert emitted[0].target == "SportClient/basic service request"
        assert emitted[0].payload["operation"] == "switch_mode"
    finally:
        await adapter.disconnect()


async def test_unitree_ros2_real_transport_requires_rclpy(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="unitree_sdk_for_test",
            command_transport="ros2_real",
        ),
    )

    with pytest.raises(UnitreeAdapterConfigurationError, match="rclpy"):
        await adapter.connect()


async def test_unitree_ros2_real_transport_requires_request_module_after_rclpy(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(__import__("sys").modules, "rclpy", SimpleNamespace())
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="unitree_sdk_for_test",
            command_transport="ros2_real",
        ),
    )

    with pytest.raises(UnitreeAdapterConfigurationError, match="unitree_api.msg"):
        await adapter.connect()


async def test_unitree_sdk_real_transport_requires_sdk_module(monkeypatch) -> None:
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="missing_unitree_sdk_for_test",
            command_transport="sdk_real",
        ),
    )

    with pytest.raises(UnitreeAdapterConfigurationError, match="not installed"):
        await adapter.connect()


async def test_unitree_sdk_real_transport_reports_unimplemented_after_sdk_import(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="unitree_sdk_for_test",
            command_transport="sdk_real",
        ),
    )

    with pytest.raises(UnitreeAdapterConfigurationError, match="DDS publisher skeleton"):
        await adapter.connect()


async def test_unitree_disabled_transport_records_blocked_execution_result(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="unitree_sdk_for_test",
            enable_motor_commands=True,
            command_transport="disabled",
        ),
    )
    await adapter.connect()
    try:
        with pytest.raises(UnitreeAdapterConfigurationError, match="transport is disabled"):
            await adapter.execute(
                SetModeCommand(
                    type=CommandType.SET_MODE,
                    seq=1,
                    timestamp=time(),
                    payload=SetModePayload(mode="manual"),
                )
            )
        result = adapter.consume_last_execution_result()
        assert result is not None
        assert result.transport == "disabled"
        assert result.command_type == "set_mode"
        assert result.status == "blocked"
        assert result.target == "disabled"
    finally:
        await adapter.disconnect()


def test_describe_unitree_transport_capability_reports_real_transport_blockers(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(__import__("sys").modules, "rclpy", SimpleNamespace())
    monkeypatch.setitem(__import__("sys").modules, "unitree_api.msg", SimpleNamespace())
    capability = describe_unitree_transport_capability(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="unitree_sdk_for_test",
            enable_motor_commands=False,
            command_transport="ros2_real",
        ),
        env={"ROS_DISTRO": "humble", "RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp"},
    )

    assert capability.transport == "ros2_real"
    assert capability.environment_ready is True
    assert capability.binding_implemented is True
    assert capability.ready is False
    assert "G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS is false" in capability.blockers
