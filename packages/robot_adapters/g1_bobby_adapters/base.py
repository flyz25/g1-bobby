from __future__ import annotations

from typing import Protocol

from g1_bobby_contracts.commands import CommandEnvelope
from g1_bobby_contracts.state import RobotState


class RobotAdapter(Protocol):
    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def get_state(self) -> RobotState: ...

    async def execute(self, command: CommandEnvelope) -> None: ...

    async def emergency_stop(self) -> None: ...

    async def reset_emergency_stop(self) -> bool: ...
