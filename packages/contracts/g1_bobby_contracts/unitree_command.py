from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .commands import CommandEnvelope, CommandType


class UnitreeCommandPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=0)
    type: str
    transport: str = "dry_run"
    action: str
    unitree_target: str
    payload: dict[str, Any]


class UnitreeCommandPlanRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded_at: float
    source: str
    stale: bool = False
    plan: UnitreeCommandPlan


def translate_unitree_command(command: CommandEnvelope) -> UnitreeCommandPlan:
    if command.type == CommandType.HEARTBEAT:
        return UnitreeCommandPlan(
            seq=command.seq,
            type=str(command.type),
            action="bridge.keepalive",
            unitree_target="session",
            payload={
                "client_id": command.payload.client_id,
                "timestamp": command.timestamp,
            },
        )

    if command.type == CommandType.SET_MODE:
        return UnitreeCommandPlan(
            seq=command.seq,
            type=str(command.type),
            action="bridge.set_mode",
            unitree_target="motion_mode",
            payload={"mode": command.payload.mode},
        )

    if command.type == CommandType.MOVE_VELOCITY:
        return UnitreeCommandPlan(
            seq=command.seq,
            type=str(command.type),
            action="motion.velocity",
            unitree_target="base_velocity",
            payload={
                "linear_x": command.payload.linear_x,
                "linear_y": command.payload.linear_y,
                "angular_z": command.payload.angular_z,
                "duration_ms": command.payload.duration_ms,
            },
        )

    if command.type == CommandType.STOP:
        return UnitreeCommandPlan(
            seq=command.seq,
            type=str(command.type),
            action="motion.stop",
            unitree_target="base_velocity",
            payload={
                "reason": command.payload.reason,
                "linear_x": 0.0,
                "linear_y": 0.0,
                "angular_z": 0.0,
            },
        )

    if command.type == CommandType.ESTOP:
        return UnitreeCommandPlan(
            seq=command.seq,
            type=str(command.type),
            action="safety.estop",
            unitree_target="motion_gate",
            payload={"reason": command.payload.reason},
        )

    raise ValueError(f"unsupported command type: {command.type}")
