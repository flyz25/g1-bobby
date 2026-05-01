from __future__ import annotations

from enum import StrEnum
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .state import RobotState


class ServerEventType(StrEnum):
    ACK = "ack"
    REJECT = "reject"
    STATE = "state"
    TELEMETRY = "telemetry"


class ErrorCode(StrEnum):
    AUTH_FAILED = "auth_failed"
    INVALID_MESSAGE = "invalid_message"
    RATE_LIMITED = "rate_limited"
    REPLAYED_COMMAND = "replayed_command"
    SAFETY_REJECTED = "safety_rejected"
    SESSION_BUSY = "session_busy"
    STALE_COMMAND = "stale_command"
    EXECUTION_FAILED = "execution_failed"


class AckEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.ACK] = ServerEventType.ACK
    seq: int | None = None
    command_type: str
    message: str = "accepted"


class RejectEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.REJECT] = ServerEventType.REJECT
    seq: int | None = None
    code: ErrorCode
    reason: str


class StateEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.STATE] = ServerEventType.STATE
    state: RobotState


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.TELEMETRY] = ServerEventType.TELEMETRY
    state: RobotState
    accepted_commands: int = Field(ge=0)
    rejected_commands: int = Field(ge=0)


ServerEvent = Union[AckEvent, RejectEvent, StateEvent, TelemetryEvent]
