from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from g1_bobby_adapters import RobotAdapter, create_robot_adapter
from g1_bobby_safety import SafetyValidator

from .config import Settings


@dataclass
class Runtime:
    adapter: RobotAdapter
    safety: SafetyValidator
    adapter_name: str
    accepted_commands: int = 0
    rejected_commands: int = 0
    active_operator_session_id: str | None = None
    _operator_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @classmethod
    async def create(cls, settings: Settings | None = None) -> "Runtime":
        resolved_settings = settings or Settings()
        adapter = create_robot_adapter(
            str(resolved_settings.robot_adapter),
            unitree_config=resolved_settings.unitree_config(),
        )
        await adapter.connect()
        return cls(
            adapter=adapter,
            safety=SafetyValidator(resolved_settings.safety_limits()),
            adapter_name=str(resolved_settings.robot_adapter),
        )

    @property
    def active_operator_connected(self) -> bool:
        return self.active_operator_session_id is not None

    async def claim_operator_session(self, session_id: str) -> bool:
        async with self._operator_lock:
            if self.active_operator_session_id is None:
                self.active_operator_session_id = session_id
                return True
            return self.active_operator_session_id == session_id

    async def release_operator_session(self, session_id: str) -> None:
        async with self._operator_lock:
            if self.active_operator_session_id == session_id:
                self.active_operator_session_id = None

    def record_accepted_command(self) -> None:
        self.accepted_commands += 1

    def record_rejected_command(self) -> None:
        self.rejected_commands += 1
