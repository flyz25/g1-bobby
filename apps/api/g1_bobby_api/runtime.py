from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
from time import time
from typing import Any

from g1_bobby_adapters import RobotAdapter, create_robot_adapter
from g1_bobby_contracts import (
    CommandEnvelope,
    RobotState,
    UnitreeCommandPlan,
    UnitreeDdsSnapshot,
    translate_unitree_command,
)
from pydantic import ValidationError
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
    unitree_command_plans: int = 0
    unitree_command_plan_recorded_at: float | None = None
    unitree_command_plan_history_size: int = 10
    unitree_state_cache_path: Path = field(default_factory=lambda: Path(".runtime/unitree_state.json"))
    unitree_command_plan_cache_path: Path = field(
        default_factory=lambda: Path(".runtime/unitree_command_plans.jsonl")
    )
    unitree_state_ttl_s: float = 2.0
    _unitree_state: UnitreeDdsSnapshot | None = field(default=None, init=False, repr=False)
    _last_unitree_command_plan: UnitreeCommandPlan | None = field(default=None, init=False, repr=False)
    _unitree_command_plan_history: list[UnitreeCommandPlan] = field(default_factory=list, init=False, repr=False)
    _unitree_state_restored: bool = field(default=False, init=False, repr=False)
    _operator_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _unitree_state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _unitree_command_plan_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @classmethod
    async def create(cls, settings: Settings | None = None) -> "Runtime":
        resolved_settings = settings or Settings()
        adapter = create_robot_adapter(
            str(resolved_settings.robot_adapter),
            unitree_config=resolved_settings.unitree_config(),
        )
        await adapter.connect()
        runtime = cls(
            adapter=adapter,
            safety=SafetyValidator(resolved_settings.safety_limits()),
            adapter_name=str(resolved_settings.robot_adapter),
            unitree_state_cache_path=resolved_settings.unitree_state_cache_path,
            unitree_command_plan_cache_path=resolved_settings.unitree_command_plan_cache_path,
            unitree_state_ttl_s=resolved_settings.unitree_state_ttl_s,
            unitree_command_plan_history_size=resolved_settings.unitree_command_plan_history_size,
        )
        await runtime.load_persisted_unitree_state()
        await runtime.load_persisted_unitree_command_plans()
        return runtime

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

    def _project_unitree_pose_label(self, snapshot: UnitreeDdsSnapshot) -> str:
        sport_state = snapshot.sport_mode_state or {}
        position = sport_state.get("position") if isinstance(sport_state, dict) else None
        if isinstance(position, list) and len(position) >= 3:
            x, y, z = position[:3]
            if all(isinstance(value, int | float) for value in (x, y, z)):
                return f"unitree-{snapshot.dds.robot} x={x:.2f} y={y:.2f} z={z:.2f}"
        return f"unitree-{snapshot.dds.robot}-{snapshot.status}"

    def _project_state(self, state: RobotState, snapshot: UnitreeDdsSnapshot | None) -> RobotState:
        if snapshot is None:
            return state

        projected = state.model_copy(deep=True)
        projected.connected = snapshot.status == "receiving" and not snapshot.stale
        projected.last_state_at = snapshot.timestamp_s
        projected.pose_label = self._project_unitree_pose_label(snapshot)
        projected.obstacle_distance_m = None
        return projected

    def _decorate_unitree_state(self, snapshot: UnitreeDdsSnapshot) -> UnitreeDdsSnapshot:
        decorated = snapshot.model_copy(deep=True)
        decorated.source = "restored" if self._unitree_state_restored else "live"
        decorated.stale = (time() - snapshot.timestamp_s) > self.unitree_state_ttl_s
        return decorated

    def _persist_unitree_state(self, snapshot: UnitreeDdsSnapshot) -> None:
        self.unitree_state_cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.unitree_state_cache_path.with_suffix(f"{self.unitree_state_cache_path.suffix}.tmp")
        tmp_path.write_text(snapshot.model_dump_json(), encoding="utf-8")
        tmp_path.replace(self.unitree_state_cache_path)

    def _persist_unitree_command_plan_history(self) -> None:
        self.unitree_command_plan_cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.unitree_command_plan_cache_path.with_suffix(f"{self.unitree_command_plan_cache_path.suffix}.tmp")
        payload = "\n".join(
            json.dumps(
                {
                    "recorded_at": self.unitree_command_plan_recorded_at if index == len(self._unitree_command_plan_history) - 1 else None,
                    "plan": plan.model_dump(mode="json"),
                }
            )
            for index, plan in enumerate(self._unitree_command_plan_history)
        )
        tmp_path.write_text(f"{payload}\n" if payload else "", encoding="utf-8")
        tmp_path.replace(self.unitree_command_plan_cache_path)

    async def record_unitree_state(self, snapshot: UnitreeDdsSnapshot) -> None:
        async with self._unitree_state_lock:
            self._unitree_state = snapshot
            self._unitree_state_restored = False
            self.unitree_state_updates += 1
            self.unitree_state_received_at = time()
            self._persist_unitree_state(snapshot)

    async def load_persisted_unitree_state(self) -> bool:
        if not self.unitree_state_cache_path.exists():
            return False
        try:
            snapshot = UnitreeDdsSnapshot.model_validate_json(
                self.unitree_state_cache_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, json.JSONDecodeError):
            return False

        async with self._unitree_state_lock:
            self._unitree_state = snapshot
            self._unitree_state_restored = True
            self.unitree_state_updates = 1
            self.unitree_state_received_at = time()
        return True

    async def load_persisted_unitree_command_plans(self) -> bool:
        if not self.unitree_command_plan_cache_path.exists():
            return False

        entries: list[tuple[UnitreeCommandPlan, float | None]] = []
        try:
            for raw_line in self.unitree_command_plan_cache_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                payload = json.loads(raw_line)
                entries.append(
                    (
                        UnitreeCommandPlan.model_validate(payload["plan"]),
                        payload.get("recorded_at"),
                    )
                )
        except (OSError, ValidationError, json.JSONDecodeError, KeyError, TypeError):
            return False

        if not entries:
            return False

        retained = entries[-self.unitree_command_plan_history_size :]
        async with self._unitree_command_plan_lock:
            self._unitree_command_plan_history = [plan for plan, _ in retained]
            self._last_unitree_command_plan = self._unitree_command_plan_history[-1]
            self.unitree_command_plans = len(self._unitree_command_plan_history)
            self.unitree_command_plan_recorded_at = retained[-1][1]
        return True

    async def get_unitree_state(self) -> UnitreeDdsSnapshot | None:
        async with self._unitree_state_lock:
            return self._decorate_unitree_state(self._unitree_state) if self._unitree_state else None

    async def get_display_state(self) -> RobotState:
        state = await self.adapter.get_state()
        return self._project_state(state, await self.get_unitree_state())

    async def record_unitree_command_plan(self, command: CommandEnvelope) -> UnitreeCommandPlan:
        plan = translate_unitree_command(command)
        async with self._unitree_command_plan_lock:
            self._last_unitree_command_plan = plan
            self._unitree_command_plan_history.append(plan)
            if len(self._unitree_command_plan_history) > self.unitree_command_plan_history_size:
                self._unitree_command_plan_history = self._unitree_command_plan_history[
                    -self.unitree_command_plan_history_size :
                ]
            self.unitree_command_plans += 1
            self.unitree_command_plan_recorded_at = time()
            self._persist_unitree_command_plan_history()
        return plan

    async def get_last_unitree_command_plan(self) -> UnitreeCommandPlan | None:
        async with self._unitree_command_plan_lock:
            return self._last_unitree_command_plan.model_copy(deep=True) if self._last_unitree_command_plan else None

    async def get_unitree_command_plan_history(self) -> list[UnitreeCommandPlan]:
        async with self._unitree_command_plan_lock:
            return [plan.model_copy(deep=True) for plan in self._unitree_command_plan_history]

    async def unitree_command_plan_status(self) -> dict[str, object]:
        async with self._unitree_command_plan_lock:
            return {
                "plans": self.unitree_command_plans,
                "last_recorded_at": self.unitree_command_plan_recorded_at,
                "available": self._last_unitree_command_plan is not None,
                "retained": len(self._unitree_command_plan_history),
                "history_size": self.unitree_command_plan_history_size,
            }

    async def unitree_state_status(self) -> dict[str, object]:
        async with self._unitree_state_lock:
            age_s = None
            if self.unitree_state_received_at is not None:
                age_s = round(time() - self.unitree_state_received_at, 3)
            snapshot = self._decorate_unitree_state(self._unitree_state) if self._unitree_state else None
            return {
                "updates": self.unitree_state_updates,
                "last_received_at": self.unitree_state_received_at,
                "age_s": age_s,
                "status": snapshot.status if snapshot else "not_available",
                "source": snapshot.source if snapshot else None,
                "stale": snapshot.stale if snapshot else None,
            }
