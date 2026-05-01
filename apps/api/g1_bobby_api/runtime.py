from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from time import time

from g1_bobby_adapters import RobotAdapter, create_robot_adapter
from g1_bobby_contracts import UnitreeDdsSnapshot
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
    unitree_state_updates: int = 0
    unitree_state_received_at: float | None = None
    _unitree_state: UnitreeDdsSnapshot | None = field(default=None, init=False, repr=False)
    _operator_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _unitree_state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

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

    async def record_unitree_state(self, snapshot: UnitreeDdsSnapshot) -> None:
        async with self._unitree_state_lock:
            self._unitree_state = snapshot
            self.unitree_state_updates += 1
            self.unitree_state_received_at = time()

    async def get_unitree_state(self) -> UnitreeDdsSnapshot | None:
        async with self._unitree_state_lock:
            return self._unitree_state.model_copy(deep=True) if self._unitree_state else None

    async def unitree_state_status(self) -> dict[str, object]:
        async with self._unitree_state_lock:
            age_s = None
            if self.unitree_state_received_at is not None:
                age_s = round(time() - self.unitree_state_received_at, 3)
            return {
                "updates": self.unitree_state_updates,
                "last_received_at": self.unitree_state_received_at,
                "age_s": age_s,
                "status": self._unitree_state.status if self._unitree_state else "not_available",
            }
