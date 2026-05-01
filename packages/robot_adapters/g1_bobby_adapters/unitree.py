from __future__ import annotations

from g1_bobby_contracts.commands import CommandEnvelope
from g1_bobby_contracts.state import RobotState


class UnitreeAdapter:
    """Placeholder boundary for the real Unitree SDK/ROS2 adapter.

    This class intentionally does not send motor commands. The mock-first MVP
    must stabilize command contracts and safety validation before real hardware
    integration is added.
    """

    async def connect(self) -> None:
        raise NotImplementedError("Unitree hardware adapter is not implemented in MVP")

    async def disconnect(self) -> None:
        raise NotImplementedError("Unitree hardware adapter is not implemented in MVP")

    async def get_state(self) -> RobotState:
        raise NotImplementedError("Unitree hardware adapter is not implemented in MVP")

    async def execute(self, command: CommandEnvelope) -> None:
        raise NotImplementedError("Unitree hardware adapter is not implemented in MVP")

    async def emergency_stop(self) -> None:
        raise NotImplementedError("Unitree hardware adapter is not implemented in MVP")

