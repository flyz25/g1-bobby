from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Protocol

from g1_bobby_contracts import CommandEnvelope, UnitreeCommandPlan, UnitreeCommandPlanRecord, translate_unitree_command


class UnitreeCommandPublisher(Protocol):
    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def publish(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord: ...


class UnitreeTransportError(RuntimeError):
    """Base error for Unitree command transport publishing."""


class UnitreeTransportConfigurationError(UnitreeTransportError):
    """Raised when the chosen Unitree command transport is not wired."""


def build_unitree_command_plan_record(
    command: CommandEnvelope,
    *,
    event_id: int,
    transport: str,
) -> UnitreeCommandPlanRecord:
    translated = translate_unitree_command(command)
    plan = UnitreeCommandPlan(
        seq=translated.seq,
        type=translated.type,
        transport=transport,
        action=translated.action,
        unitree_target=translated.unitree_target,
        payload=dict(translated.payload),
    )
    return UnitreeCommandPlanRecord(
        event_id=event_id,
        recorded_at=time(),
        source="live",
        stale=False,
        plan=plan,
    )


@dataclass(frozen=True)
class DryRunUnitreeCommandPublisher:
    _next_event_id: list[int] = field(default_factory=lambda: [1])
    _published: list[UnitreeCommandPlanRecord] = field(default_factory=list)

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def publish(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord:
        record = build_unitree_command_plan_record(
            command,
            event_id=self._next_event_id[0],
            transport="dry_run",
        )
        self._next_event_id[0] += 1
        self._published.append(record)
        return record

    def published_records(self) -> list[UnitreeCommandPlanRecord]:
        return [record.model_copy(deep=True) for record in self._published]


class DisabledUnitreeCommandPublisher:
    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def publish(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord:
        raise UnitreeTransportConfigurationError(
            "Unitree command transport is disabled; keep G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS=false "
            "or select a non-disabled publisher before attempting execution"
        )
