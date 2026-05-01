from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="G1_BOBBY_", env_file=".env", extra="ignore")

    operator_token: str = Field(default="dev-operator-token")
    telemetry_interval_s: float = Field(default=0.5, gt=0.0)
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])

