from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from ._compat import StrEnum


class CommandType(StrEnum):
    HEARTBEAT = "heartbeat"
    MOVE_VELOCITY = "move_velocity"
    STOP = "stop"
    ESTOP = "estop"
    SET_MODE = "set_mode"


class HeartbeatPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(min_length=1, max_length=80)


class MoveVelocityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    linear_x: float = Field(ge=-1.0, le=1.0)
    linear_y: float = Field(ge=-1.0, le=1.0)
    angular_z: float = Field(ge=-1.0, le=1.0)
    duration_ms: int = Field(default=100, ge=20, le=1000)


class StopPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="operator_stop", max_length=120)


class EmergencyStopPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="operator_estop", max_length=120)


class SetModePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["idle", "manual", "assist"]


class HeartbeatCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[CommandType.HEARTBEAT]
    seq: int = Field(ge=0)
    timestamp: float = Field(gt=0)
    payload: HeartbeatPayload


class MoveVelocityCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[CommandType.MOVE_VELOCITY]
    seq: int = Field(ge=0)
    timestamp: float = Field(gt=0)
    payload: MoveVelocityPayload


class StopCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[CommandType.STOP]
    seq: int = Field(ge=0)
    timestamp: float = Field(gt=0)
    payload: StopPayload = Field(default_factory=StopPayload)


class EmergencyStopCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[CommandType.ESTOP]
    seq: int = Field(ge=0)
    timestamp: float = Field(gt=0)
    payload: EmergencyStopPayload = Field(default_factory=EmergencyStopPayload)


class SetModeCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[CommandType.SET_MODE]
    seq: int = Field(ge=0)
    timestamp: float = Field(gt=0)
    payload: SetModePayload


CommandEnvelope = Annotated[
    Union[
        HeartbeatCommand,
        MoveVelocityCommand,
        StopCommand,
        EmergencyStopCommand,
        SetModeCommand,
    ],
    Field(discriminator="type"),
]
