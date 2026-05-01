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
        assert emitted[0].target == "/lowcmd"
        assert emitted[0].payload["velocity"]["linear_x"] == 0.0
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


async def test_unitree_ros2_real_transport_reports_unimplemented_after_rclpy(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(__import__("sys").modules, "rclpy", SimpleNamespace())
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="unitree_sdk_for_test",
            command_transport="ros2_real",
        ),
    )

    with pytest.raises(UnitreeAdapterConfigurationError, match="not implemented yet"):
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
