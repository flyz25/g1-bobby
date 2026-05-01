from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from g1_bobby_adapters import UnitreeAdapterConfig
from g1_bobby_safety import SafetyLimits


class RobotAdapterName(StrEnum):
    MOCK = "mock"
    UNITREE = "unitree"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="G1_BOBBY_", env_file=".env", extra="ignore")

    operator_token: str = Field(default="dev-operator-token")
    telemetry_interval_s: float = Field(default=0.5, gt=0.0)
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    robot_adapter: RobotAdapterName = RobotAdapterName.MOCK

    unitree_network_interface: str | None = None
    unitree_sdk_module: str = Field(default="unitree_sdk2py", min_length=1)
    unitree_enable_motor_commands: bool = False

    safety_max_linear_mps: float = Field(default=0.35, gt=0.0)
    safety_max_angular_radps: float = Field(default=0.6, gt=0.0)
    safety_min_obstacle_distance_m: float = Field(default=0.5, ge=0.0)
    safety_state_ttl_s: float = Field(default=1.0, gt=0.0)
    safety_heartbeat_ttl_s: float = Field(default=2.0, gt=0.0)

    def unitree_config(self) -> UnitreeAdapterConfig:
        return UnitreeAdapterConfig(
            network_interface=self.unitree_network_interface,
            sdk_module=self.unitree_sdk_module,
            enable_motor_commands=self.unitree_enable_motor_commands,
        )

    def safety_limits(self) -> SafetyLimits:
        return SafetyLimits(
            max_linear_mps=self.safety_max_linear_mps,
            max_angular_radps=self.safety_max_angular_radps,
            min_obstacle_distance_m=self.safety_min_obstacle_distance_m,
            state_ttl_s=self.safety_state_ttl_s,
            heartbeat_ttl_s=self.safety_heartbeat_ttl_s,
        )
