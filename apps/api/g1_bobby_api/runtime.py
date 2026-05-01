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
    RejectEvent,
    RejectedCommandRecord,
    RobotState,
    UnitreeCommandPlan,
    UnitreeCommandPlanRecord,
    UnitreeExecutionPlan,
    UnitreeExecutionPlanRecord,
    UnitreeExecutionResult,
    UnitreeExecutionResultRecord,
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
    unitree_execution_plans: int = 0
    unitree_execution_plan_recorded_at: float | None = None
    unitree_execution_results: int = 0
    unitree_execution_result_recorded_at: float | None = None
    rejected_command_records: int = 0
    rejected_command_recorded_at: float | None = None
    unitree_command_plan_history_size: int = 10
    unitree_execution_plan_history_size: int = 10
    unitree_execution_result_history_size: int = 10
    rejected_command_history_size: int = 20
    unitree_state_cache_path: Path = field(default_factory=lambda: Path(".runtime/unitree_state.json"))
    unitree_command_plan_cache_path: Path = field(
        default_factory=lambda: Path(".runtime/unitree_command_plans.jsonl")
    )
    unitree_execution_plan_cache_path: Path = field(
        default_factory=lambda: Path(".runtime/unitree_execution_plans.jsonl")
    )
    unitree_execution_result_cache_path: Path = field(
        default_factory=lambda: Path(".runtime/unitree_execution_results.jsonl")
    )
    rejected_command_cache_path: Path = field(default_factory=lambda: Path(".runtime/rejected_commands.jsonl"))
    unitree_state_ttl_s: float = 2.0
    unitree_command_plan_ttl_s: float = 10.0
    unitree_execution_plan_ttl_s: float = 10.0
    unitree_execution_result_ttl_s: float = 10.0
    rejected_command_ttl_s: float = 10.0
    _next_audit_event_id: int = field(default=1, init=False, repr=False)
    _unitree_state: UnitreeDdsSnapshot | None = field(default=None, init=False, repr=False)
    _last_unitree_command_plan: UnitreeCommandPlanRecord | None = field(default=None, init=False, repr=False)
    _unitree_command_plan_history: list[UnitreeCommandPlanRecord] = field(default_factory=list, init=False, repr=False)
    _unitree_command_plan_restored: bool = field(default=False, init=False, repr=False)
    _unitree_command_plan_subscribers: set[asyncio.Queue[UnitreeCommandPlanRecord]] = field(
        default_factory=set,
        init=False,
        repr=False,
    )
    _last_unitree_execution_plan: UnitreeExecutionPlanRecord | None = field(default=None, init=False, repr=False)
    _unitree_execution_plan_history: list[UnitreeExecutionPlanRecord] = field(default_factory=list, init=False, repr=False)
    _unitree_execution_plan_restored: bool = field(default=False, init=False, repr=False)
    _unitree_execution_plan_subscribers: set[asyncio.Queue[UnitreeExecutionPlanRecord]] = field(
        default_factory=set,
        init=False,
        repr=False,
    )
    _last_unitree_execution_result: UnitreeExecutionResultRecord | None = field(default=None, init=False, repr=False)
    _unitree_execution_result_history: list[UnitreeExecutionResultRecord] = field(default_factory=list, init=False, repr=False)
    _unitree_execution_result_restored: bool = field(default=False, init=False, repr=False)
    _unitree_execution_result_subscribers: set[asyncio.Queue[UnitreeExecutionResultRecord]] = field(
        default_factory=set,
        init=False,
        repr=False,
    )
    _last_rejected_command: RejectedCommandRecord | None = field(default=None, init=False, repr=False)
    _rejected_command_history: list[RejectedCommandRecord] = field(default_factory=list, init=False, repr=False)
    _rejected_command_restored: bool = field(default=False, init=False, repr=False)
    _rejected_command_subscribers: set[asyncio.Queue[RejectedCommandRecord]] = field(
        default_factory=set,
        init=False,
        repr=False,
    )
    _unitree_state_restored: bool = field(default=False, init=False, repr=False)
    _operator_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _unitree_state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _unitree_command_plan_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _unitree_execution_plan_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _unitree_execution_result_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _rejected_command_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

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
            unitree_execution_plan_cache_path=resolved_settings.unitree_execution_plan_cache_path,
            unitree_execution_result_cache_path=resolved_settings.unitree_execution_result_cache_path,
            rejected_command_cache_path=resolved_settings.rejected_command_cache_path,
            unitree_state_ttl_s=resolved_settings.unitree_state_ttl_s,
            unitree_command_plan_ttl_s=resolved_settings.unitree_command_plan_ttl_s,
            unitree_execution_plan_ttl_s=resolved_settings.unitree_execution_plan_ttl_s,
            unitree_execution_result_ttl_s=resolved_settings.unitree_execution_result_ttl_s,
            rejected_command_ttl_s=resolved_settings.rejected_command_ttl_s,
            unitree_command_plan_history_size=resolved_settings.unitree_command_plan_history_size,
            unitree_execution_plan_history_size=resolved_settings.unitree_execution_plan_history_size,
            unitree_execution_result_history_size=resolved_settings.unitree_execution_result_history_size,
            rejected_command_history_size=resolved_settings.rejected_command_history_size,
        )
        await runtime.load_persisted_unitree_state()
        await runtime.load_persisted_unitree_command_plans()
        await runtime.load_persisted_unitree_execution_plans()
        await runtime.load_persisted_unitree_execution_results()
        await runtime.load_persisted_rejected_commands()
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

    def _allocate_audit_event_id(self) -> int:
        event_id = self._next_audit_event_id
        self._next_audit_event_id += 1
        return event_id

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
                    "event_id": record.event_id,
                    "recorded_at": record.recorded_at,
                    "plan": record.plan.model_dump(mode="json"),
                }
            )
            for record in self._unitree_command_plan_history
        )
        tmp_path.write_text(f"{payload}\n" if payload else "", encoding="utf-8")
        tmp_path.replace(self.unitree_command_plan_cache_path)

    def _persist_rejected_command_history(self) -> None:
        self.rejected_command_cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.rejected_command_cache_path.with_suffix(f"{self.rejected_command_cache_path.suffix}.tmp")
        payload = "\n".join(
            json.dumps(
                {
                    "event_id": record.event_id,
                    "recorded_at": record.recorded_at,
                    "rejection": record.rejection.model_dump(mode="json"),
                    "command_type": record.command_type,
                }
            )
            for record in self._rejected_command_history
        )
        tmp_path.write_text(f"{payload}\n" if payload else "", encoding="utf-8")
        tmp_path.replace(self.rejected_command_cache_path)

    def _persist_unitree_execution_plan_history(self) -> None:
        self.unitree_execution_plan_cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.unitree_execution_plan_cache_path.with_suffix(
            f"{self.unitree_execution_plan_cache_path.suffix}.tmp"
        )
        payload = "\n".join(
            json.dumps(
                {
                    "event_id": record.event_id,
                    "recorded_at": record.recorded_at,
                    "execution_plan": record.execution_plan.model_dump(mode="json"),
                }
            )
            for record in self._unitree_execution_plan_history
        )
        tmp_path.write_text(f"{payload}\n" if payload else "", encoding="utf-8")
        tmp_path.replace(self.unitree_execution_plan_cache_path)

    def _persist_unitree_execution_result_history(self) -> None:
        self.unitree_execution_result_cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.unitree_execution_result_cache_path.with_suffix(
            f"{self.unitree_execution_result_cache_path.suffix}.tmp"
        )
        payload = "\n".join(
            json.dumps(
                {
                    "event_id": record.event_id,
                    "recorded_at": record.recorded_at,
                    "execution_result": record.execution_result.model_dump(mode="json"),
                }
            )
            for record in self._unitree_execution_result_history
        )
        tmp_path.write_text(f"{payload}\n" if payload else "", encoding="utf-8")
        tmp_path.replace(self.unitree_execution_result_cache_path)

    def _decorate_unitree_command_plan_record(self, record: UnitreeCommandPlanRecord) -> UnitreeCommandPlanRecord:
        decorated = record.model_copy(deep=True)
        decorated.source = "restored" if self._unitree_command_plan_restored else "live"
        decorated.stale = (time() - decorated.recorded_at) > self.unitree_command_plan_ttl_s
        return decorated

    def _decorate_rejected_command_record(self, record: RejectedCommandRecord) -> RejectedCommandRecord:
        decorated = record.model_copy(deep=True)
        decorated.source = "restored" if self._rejected_command_restored else "live"
        decorated.stale = (time() - decorated.recorded_at) > self.rejected_command_ttl_s
        return decorated

    def _decorate_unitree_execution_plan_record(
        self,
        record: UnitreeExecutionPlanRecord,
    ) -> UnitreeExecutionPlanRecord:
        decorated = record.model_copy(deep=True)
        decorated.source = "restored" if self._unitree_execution_plan_restored else "live"
        decorated.stale = (time() - decorated.recorded_at) > self.unitree_execution_plan_ttl_s
        return decorated

    def _decorate_unitree_execution_result_record(
        self,
        record: UnitreeExecutionResultRecord,
    ) -> UnitreeExecutionResultRecord:
        decorated = record.model_copy(deep=True)
        decorated.source = "restored" if self._unitree_execution_result_restored else "live"
        decorated.stale = (time() - decorated.recorded_at) > self.unitree_execution_result_ttl_s
        return decorated

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

        entries: list[UnitreeCommandPlanRecord] = []
        try:
            for raw_line in self.unitree_command_plan_cache_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                payload = json.loads(raw_line)
                entries.append(
                    UnitreeCommandPlanRecord(
                        event_id=int(payload.get("event_id") or self._allocate_audit_event_id()),
                        recorded_at=float(payload["recorded_at"]),
                        source="restored",
                        stale=False,
                        plan=UnitreeCommandPlan.model_validate(payload["plan"]),
                    )
                )
        except (OSError, ValidationError, json.JSONDecodeError, KeyError, TypeError):
            return False

        if not entries:
            return False

        retained = entries[-self.unitree_command_plan_history_size :]
        async with self._unitree_command_plan_lock:
            self._unitree_command_plan_history = retained
            self._last_unitree_command_plan = self._unitree_command_plan_history[-1]
            self._unitree_command_plan_restored = True
            self.unitree_command_plans = len(self._unitree_command_plan_history)
            self.unitree_command_plan_recorded_at = retained[-1].recorded_at
            self._next_audit_event_id = max(self._next_audit_event_id, retained[-1].event_id + 1)
        return True

    async def load_persisted_unitree_execution_plans(self) -> bool:
        if not self.unitree_execution_plan_cache_path.exists():
            return False

        entries: list[UnitreeExecutionPlanRecord] = []
        try:
            for raw_line in self.unitree_execution_plan_cache_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                payload = json.loads(raw_line)
                entries.append(
                    UnitreeExecutionPlanRecord(
                        event_id=int(payload.get("event_id") or self._allocate_audit_event_id()),
                        recorded_at=float(payload["recorded_at"]),
                        source="restored",
                        stale=False,
                        execution_plan=UnitreeExecutionPlan.model_validate(payload["execution_plan"]),
                    )
                )
        except (OSError, ValidationError, json.JSONDecodeError, KeyError, TypeError):
            return False

        if not entries:
            return False

        retained = entries[-self.unitree_execution_plan_history_size :]
        async with self._unitree_execution_plan_lock:
            self._unitree_execution_plan_history = retained
            self._last_unitree_execution_plan = retained[-1]
            self._unitree_execution_plan_restored = True
            self.unitree_execution_plans = len(retained)
            self.unitree_execution_plan_recorded_at = retained[-1].recorded_at
            self._next_audit_event_id = max(self._next_audit_event_id, retained[-1].event_id + 1)
        return True

    async def load_persisted_unitree_execution_results(self) -> bool:
        if not self.unitree_execution_result_cache_path.exists():
            return False

        entries: list[UnitreeExecutionResultRecord] = []
        try:
            for raw_line in self.unitree_execution_result_cache_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                payload = json.loads(raw_line)
                entries.append(
                    UnitreeExecutionResultRecord(
                        event_id=int(payload.get("event_id") or self._allocate_audit_event_id()),
                        recorded_at=float(payload["recorded_at"]),
                        source="restored",
                        stale=False,
                        execution_result=UnitreeExecutionResult.model_validate(payload["execution_result"]),
                    )
                )
        except (OSError, ValidationError, json.JSONDecodeError, KeyError, TypeError):
            return False

        if not entries:
            return False

        retained = entries[-self.unitree_execution_result_history_size :]
        async with self._unitree_execution_result_lock:
            self._unitree_execution_result_history = retained
            self._last_unitree_execution_result = retained[-1]
            self._unitree_execution_result_restored = True
            self.unitree_execution_results = len(retained)
            self.unitree_execution_result_recorded_at = retained[-1].recorded_at
            self._next_audit_event_id = max(self._next_audit_event_id, retained[-1].event_id + 1)
        return True

    async def load_persisted_rejected_commands(self) -> bool:
        if not self.rejected_command_cache_path.exists():
            return False

        entries: list[RejectedCommandRecord] = []
        try:
            for raw_line in self.rejected_command_cache_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                payload = json.loads(raw_line)
                entries.append(
                    RejectedCommandRecord(
                        event_id=int(payload.get("event_id") or self._allocate_audit_event_id()),
                        recorded_at=float(payload["recorded_at"]),
                        source="restored",
                        stale=False,
                        rejection=RejectEvent.model_validate(payload["rejection"]),
                        command_type=payload.get("command_type"),
                    )
                )
        except (OSError, ValidationError, json.JSONDecodeError, KeyError, TypeError):
            return False

        if not entries:
            return False

        retained = entries[-self.rejected_command_history_size :]
        async with self._rejected_command_lock:
            self._rejected_command_history = retained
            self._last_rejected_command = retained[-1]
            self._rejected_command_restored = True
            self.rejected_command_records = len(retained)
            self.rejected_command_recorded_at = retained[-1].recorded_at
            self._next_audit_event_id = max(self._next_audit_event_id, retained[-1].event_id + 1)
        return True

    async def get_unitree_state(self) -> UnitreeDdsSnapshot | None:
        async with self._unitree_state_lock:
            return self._decorate_unitree_state(self._unitree_state) if self._unitree_state else None

    async def get_display_state(self) -> RobotState:
        state = await self.adapter.get_state()
        return self._project_state(state, await self.get_unitree_state())

    async def record_unitree_command_plan(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord:
        plan = translate_unitree_command(command)
        record = UnitreeCommandPlanRecord(
            event_id=self._allocate_audit_event_id(),
            recorded_at=time(),
            source="live",
            stale=False,
            plan=plan,
        )
        async with self._unitree_command_plan_lock:
            self._last_unitree_command_plan = record
            self._unitree_command_plan_history.append(record)
            self._unitree_command_plan_restored = False
            if len(self._unitree_command_plan_history) > self.unitree_command_plan_history_size:
                self._unitree_command_plan_history = self._unitree_command_plan_history[
                    -self.unitree_command_plan_history_size :
                ]
            self.unitree_command_plans += 1
            self.unitree_command_plan_recorded_at = record.recorded_at
            self._persist_unitree_command_plan_history()
            decorated = self._decorate_unitree_command_plan_record(record)
            for subscriber in self._unitree_command_plan_subscribers:
                subscriber.put_nowait(decorated)
        return decorated

    async def get_last_unitree_command_plan(self) -> UnitreeCommandPlanRecord | None:
        async with self._unitree_command_plan_lock:
            return (
                self._decorate_unitree_command_plan_record(self._last_unitree_command_plan)
                if self._last_unitree_command_plan
                else None
            )

    async def get_unitree_command_plan_history(self) -> list[UnitreeCommandPlanRecord]:
        async with self._unitree_command_plan_lock:
            return [self._decorate_unitree_command_plan_record(record) for record in self._unitree_command_plan_history]

    async def record_unitree_execution_plan(
        self,
        execution_plan: UnitreeExecutionPlan,
    ) -> UnitreeExecutionPlanRecord:
        record = UnitreeExecutionPlanRecord(
            event_id=self._allocate_audit_event_id(),
            recorded_at=time(),
            source="live",
            stale=False,
            execution_plan=execution_plan,
        )
        async with self._unitree_execution_plan_lock:
            self._last_unitree_execution_plan = record
            self._unitree_execution_plan_history.append(record)
            self._unitree_execution_plan_restored = False
            if len(self._unitree_execution_plan_history) > self.unitree_execution_plan_history_size:
                self._unitree_execution_plan_history = self._unitree_execution_plan_history[
                    -self.unitree_execution_plan_history_size :
                ]
            self.unitree_execution_plans += 1
            self.unitree_execution_plan_recorded_at = record.recorded_at
            self._persist_unitree_execution_plan_history()
            decorated = self._decorate_unitree_execution_plan_record(record)
            for subscriber in self._unitree_execution_plan_subscribers:
                subscriber.put_nowait(decorated)
        return decorated

    async def get_last_unitree_execution_plan(self) -> UnitreeExecutionPlanRecord | None:
        async with self._unitree_execution_plan_lock:
            return (
                self._decorate_unitree_execution_plan_record(self._last_unitree_execution_plan)
                if self._last_unitree_execution_plan
                else None
            )

    async def get_unitree_execution_plan_history(self) -> list[UnitreeExecutionPlanRecord]:
        async with self._unitree_execution_plan_lock:
            return [
                self._decorate_unitree_execution_plan_record(record)
                for record in self._unitree_execution_plan_history
            ]

    async def record_unitree_execution_result(
        self,
        execution_result: UnitreeExecutionResult,
    ) -> UnitreeExecutionResultRecord:
        record = UnitreeExecutionResultRecord(
            event_id=self._allocate_audit_event_id(),
            recorded_at=time(),
            source="live",
            stale=False,
            execution_result=execution_result,
        )
        async with self._unitree_execution_result_lock:
            self._last_unitree_execution_result = record
            self._unitree_execution_result_history.append(record)
            self._unitree_execution_result_restored = False
            if len(self._unitree_execution_result_history) > self.unitree_execution_result_history_size:
                self._unitree_execution_result_history = self._unitree_execution_result_history[
                    -self.unitree_execution_result_history_size :
                ]
            self.unitree_execution_results += 1
            self.unitree_execution_result_recorded_at = record.recorded_at
            self._persist_unitree_execution_result_history()
            decorated = self._decorate_unitree_execution_result_record(record)
            for subscriber in self._unitree_execution_result_subscribers:
                subscriber.put_nowait(decorated)
        return decorated

    async def get_last_unitree_execution_result(self) -> UnitreeExecutionResultRecord | None:
        async with self._unitree_execution_result_lock:
            return (
                self._decorate_unitree_execution_result_record(self._last_unitree_execution_result)
                if self._last_unitree_execution_result
                else None
            )

    async def get_unitree_execution_result_history(self) -> list[UnitreeExecutionResultRecord]:
        async with self._unitree_execution_result_lock:
            return [
                self._decorate_unitree_execution_result_record(record)
                for record in self._unitree_execution_result_history
            ]

    async def subscribe_unitree_execution_results(self) -> asyncio.Queue[UnitreeExecutionResultRecord]:
        queue: asyncio.Queue[UnitreeExecutionResultRecord] = asyncio.Queue()
        async with self._unitree_execution_result_lock:
            self._unitree_execution_result_subscribers.add(queue)
        return queue

    async def unsubscribe_unitree_execution_results(
        self,
        queue: asyncio.Queue[UnitreeExecutionResultRecord],
    ) -> None:
        async with self._unitree_execution_result_lock:
            self._unitree_execution_result_subscribers.discard(queue)

    async def subscribe_unitree_execution_plans(self) -> asyncio.Queue[UnitreeExecutionPlanRecord]:
        queue: asyncio.Queue[UnitreeExecutionPlanRecord] = asyncio.Queue()
        async with self._unitree_execution_plan_lock:
            self._unitree_execution_plan_subscribers.add(queue)
        return queue

    async def unsubscribe_unitree_execution_plans(
        self,
        queue: asyncio.Queue[UnitreeExecutionPlanRecord],
    ) -> None:
        async with self._unitree_execution_plan_lock:
            self._unitree_execution_plan_subscribers.discard(queue)

    async def subscribe_unitree_command_plans(self) -> asyncio.Queue[UnitreeCommandPlanRecord]:
        queue: asyncio.Queue[UnitreeCommandPlanRecord] = asyncio.Queue()
        async with self._unitree_command_plan_lock:
            self._unitree_command_plan_subscribers.add(queue)
        return queue

    async def unsubscribe_unitree_command_plans(self, queue: asyncio.Queue[UnitreeCommandPlanRecord]) -> None:
        async with self._unitree_command_plan_lock:
            self._unitree_command_plan_subscribers.discard(queue)

    async def record_rejected_command_event(
        self,
        reject_event: RejectEvent,
        command_type: str | None = None,
    ) -> RejectedCommandRecord:
        self.record_rejected_command()
        record = RejectedCommandRecord(
            event_id=self._allocate_audit_event_id(),
            recorded_at=time(),
            source="live",
            stale=False,
            rejection=reject_event,
            command_type=command_type,
        )
        async with self._rejected_command_lock:
            self._last_rejected_command = record
            self._rejected_command_history.append(record)
            self._rejected_command_restored = False
            if len(self._rejected_command_history) > self.rejected_command_history_size:
                self._rejected_command_history = self._rejected_command_history[-self.rejected_command_history_size :]
            self.rejected_command_records += 1
            self.rejected_command_recorded_at = record.recorded_at
            self._persist_rejected_command_history()
            decorated = self._decorate_rejected_command_record(record)
            for subscriber in self._rejected_command_subscribers:
                subscriber.put_nowait(decorated)
        return decorated

    async def get_last_rejected_command(self) -> RejectedCommandRecord | None:
        async with self._rejected_command_lock:
            return (
                self._decorate_rejected_command_record(self._last_rejected_command)
                if self._last_rejected_command
                else None
            )

    async def get_rejected_command_history(self) -> list[RejectedCommandRecord]:
        async with self._rejected_command_lock:
            return [self._decorate_rejected_command_record(record) for record in self._rejected_command_history]

    async def subscribe_rejected_commands(self) -> asyncio.Queue[RejectedCommandRecord]:
        queue: asyncio.Queue[RejectedCommandRecord] = asyncio.Queue()
        async with self._rejected_command_lock:
            self._rejected_command_subscribers.add(queue)
        return queue

    async def unsubscribe_rejected_commands(self, queue: asyncio.Queue[RejectedCommandRecord]) -> None:
        async with self._rejected_command_lock:
            self._rejected_command_subscribers.discard(queue)

    async def unitree_command_plan_status(self) -> dict[str, object]:
        async with self._unitree_command_plan_lock:
            last = (
                self._decorate_unitree_command_plan_record(self._last_unitree_command_plan)
                if self._last_unitree_command_plan
                else None
            )
            return {
                "plans": self.unitree_command_plans,
                "last_recorded_at": self.unitree_command_plan_recorded_at,
                "available": self._last_unitree_command_plan is not None,
                "retained": len(self._unitree_command_plan_history),
                "history_size": self.unitree_command_plan_history_size,
                "source": last.source if last else None,
                "stale": last.stale if last else None,
            }

    async def unitree_execution_plan_status(self) -> dict[str, object]:
        async with self._unitree_execution_plan_lock:
            last = (
                self._decorate_unitree_execution_plan_record(self._last_unitree_execution_plan)
                if self._last_unitree_execution_plan
                else None
            )
            return {
                "plans": self.unitree_execution_plans,
                "last_recorded_at": self.unitree_execution_plan_recorded_at,
                "available": self._last_unitree_execution_plan is not None,
                "retained": len(self._unitree_execution_plan_history),
                "history_size": self.unitree_execution_plan_history_size,
                "source": last.source if last else None,
                "stale": last.stale if last else None,
            }

    async def unitree_execution_result_status(self) -> dict[str, object]:
        async with self._unitree_execution_result_lock:
            last = (
                self._decorate_unitree_execution_result_record(self._last_unitree_execution_result)
                if self._last_unitree_execution_result
                else None
            )
            return {
                "results": self.unitree_execution_results,
                "last_recorded_at": self.unitree_execution_result_recorded_at,
                "available": self._last_unitree_execution_result is not None,
                "retained": len(self._unitree_execution_result_history),
                "history_size": self.unitree_execution_result_history_size,
                "source": last.source if last else None,
                "stale": last.stale if last else None,
            }

    async def rejected_command_status(self) -> dict[str, object]:
        async with self._rejected_command_lock:
            last = (
                self._decorate_rejected_command_record(self._last_rejected_command)
                if self._last_rejected_command
                else None
            )
            return {
                "records": self.rejected_command_records,
                "last_recorded_at": self.rejected_command_recorded_at,
                "available": self._last_rejected_command is not None,
                "retained": len(self._rejected_command_history),
                "history_size": self.rejected_command_history_size,
                "source": last.source if last else None,
                "stale": last.stale if last else None,
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
