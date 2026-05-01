from __future__ import annotations

from enum import StrEnum
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .state import RobotState
from .unitree_command import (
    UnitreeCommandPlanRecord,
    UnitreeExecutionPlanRecord,
    UnitreeExecutionResultRecord,
)
from .unitree import UnitreeDdsSnapshot


class ServerEventType(StrEnum):
    ACK = "ack"
    COMMAND_PLAN = "command_plan"
    EXECUTION_PLAN = "execution_plan"
    EXECUTION_RESULT = "execution_result"
    REJECT = "reject"
    REJECTED_COMMAND = "rejected_command"
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
    unitree_command_plan: UnitreeCommandPlanRecord | None = None
    unitree_execution_plan: UnitreeExecutionPlanRecord | None = None
    unitree_execution_result: UnitreeExecutionResultRecord | None = None


class RejectEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.REJECT] = ServerEventType.REJECT
    seq: int | None = None
    code: ErrorCode
    reason: str
    unitree_execution_result: UnitreeExecutionResultRecord | None = None


class RejectedCommandRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: int = Field(ge=1)
    recorded_at: float
    source: str
    stale: bool = False
    rejection: RejectEvent
    command_type: str | None = None


class CommandPlanEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.COMMAND_PLAN] = ServerEventType.COMMAND_PLAN
    unitree_command_plan: UnitreeCommandPlanRecord


class RejectedCommandEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.REJECTED_COMMAND] = ServerEventType.REJECTED_COMMAND
    rejected_command: RejectedCommandRecord


class ExecutionPlanEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.EXECUTION_PLAN] = ServerEventType.EXECUTION_PLAN
    unitree_execution_plan: UnitreeExecutionPlanRecord


class ExecutionResultEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.EXECUTION_RESULT] = ServerEventType.EXECUTION_RESULT
    unitree_execution_result: UnitreeExecutionResultRecord


class StateEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.STATE] = ServerEventType.STATE
    state: RobotState
    unitree_state: UnitreeDdsSnapshot | None = None


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ServerEventType.TELEMETRY] = ServerEventType.TELEMETRY
    state: RobotState
    accepted_commands: int = Field(ge=0)
    rejected_commands: int = Field(ge=0)
    unitree_state: UnitreeDdsSnapshot | None = None


ServerEvent = Union[
    AckEvent,
    CommandPlanEvent,
    ExecutionPlanEvent,
    ExecutionResultEvent,
    RejectEvent,
    RejectedCommandEvent,
    StateEvent,
    TelemetryEvent,
]
