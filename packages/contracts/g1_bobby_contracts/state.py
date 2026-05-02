from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ._compat import StrEnum


class ControlMode(StrEnum):
    IDLE = "idle"
    MANUAL = "manual"
    ASSIST = "assist"


class RobotState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connected: bool = False
    estop_engaged: bool = False
    mode: ControlMode = ControlMode.IDLE
    battery_percent: float = Field(default=100.0, ge=0.0, le=100.0)
    obstacle_distance_m: float | None = Field(default=None, ge=0.0)
    last_state_at: float | None = Field(default=None, gt=0)
    last_heartbeat_at: float | None = Field(default=None, gt=0)
    pose_label: str = "mock-origin"
