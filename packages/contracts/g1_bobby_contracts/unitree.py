from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UnitreeDdsInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain_id: int
    interface: str
    robot: str
    topics: dict[str, str]


class UnitreeSampleCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_state: int = Field(default=0, ge=0)
    sport_mode_state: int = Field(default=0, ge=0)


class UnitreeSampleAges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_state: float | None = Field(default=None, ge=0)
    sport_mode_state: float | None = Field(default=None, ge=0)


class UnitreeDdsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    source: str = "live"
    stale: bool = False
    timestamp_s: float = Field(gt=0)
    dds: UnitreeDdsInfo
    sample_counts: UnitreeSampleCounts
    ages_s: UnitreeSampleAges
    low_state: dict[str, Any] | None = None
    sport_mode_state: dict[str, Any] | None = None
