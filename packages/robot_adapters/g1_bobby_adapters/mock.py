from __future__ import annotations

from time import time

from g1_bobby_contracts.commands import (
    CommandEnvelope,
    CommandType,
    HeartbeatCommand,
    SetModeCommand,
)
from g1_bobby_contracts.state import ControlMode, RobotState


class MockRobotAdapter:
    def __init__(self) -> None:
        now = time()
        self._state = RobotState(
            connected=False,
            estop_engaged=False,
            mode=ControlMode.IDLE,
            battery_percent=100.0,
            obstacle_distance_m=2.0,
            last_state_at=now,
            last_heartbeat_at=None,
        )
        self.accepted_commands: list[CommandEnvelope] = []

    async def connect(self) -> None:
        self._state.connected = True
        self._state.last_state_at = time()

    async def disconnect(self) -> None:
        self._state.connected = False
        self._state.last_state_at = time()

    async def get_state(self) -> RobotState:
        self._state.last_state_at = time()
        return self._state.model_copy()

    async def execute(self, command: CommandEnvelope) -> None:
        self.accepted_commands.append(command)
        self._state.last_state_at = time()

        if isinstance(command, HeartbeatCommand):
            self._state.last_heartbeat_at = time()
            return

        if isinstance(command, SetModeCommand):
            self._state.mode = ControlMode(command.payload.mode)
            return

        if command.type == CommandType.STOP:
            self._state.mode = ControlMode.MANUAL
            return

        if command.type == CommandType.ESTOP:
            await self.emergency_stop()

    async def emergency_stop(self) -> None:
        self._state.estop_engaged = True
        self._state.mode = ControlMode.IDLE
        self._state.last_state_at = time()

    async def reset_emergency_stop(self) -> bool:
        if not self._state.connected:
            return False
        self._state.estop_engaged = False
        self._state.mode = ControlMode.IDLE
        self._state.last_state_at = time()
        return True

