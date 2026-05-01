from time import time

from g1_bobby_contracts.commands import (
    CommandType,
    SetModeCommand,
    SetModePayload,
    StopCommand,
    StopPayload,
)
from g1_bobby_contracts.state import ControlMode
from g1_bobby_adapters import MockRobotAdapter


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
