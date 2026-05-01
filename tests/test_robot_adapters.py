from types import SimpleNamespace
from time import time

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
)


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
