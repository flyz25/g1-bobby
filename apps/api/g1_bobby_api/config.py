from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from g1_bobby_adapters import UnitreeAdapterConfig
from g1_bobby_contracts._compat import StrEnum
from g1_bobby_safety import SafetyLimits

from .command_gate import CommandGateLimits


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
    unitree_command_transport: str = Field(default="disabled", min_length=1)
    unitree_state_cache_path: Path = Path(".runtime/unitree_state.json")
    unitree_command_plan_cache_path: Path = Path(".runtime/unitree_command_plans.jsonl")
    unitree_execution_plan_cache_path: Path = Path(".runtime/unitree_execution_plans.jsonl")
    unitree_execution_result_cache_path: Path = Path(".runtime/unitree_execution_results.jsonl")
    rejected_command_cache_path: Path = Path(".runtime/rejected_commands.jsonl")
    unitree_state_ttl_s: float = Field(default=2.0, gt=0.0)
    unitree_command_plan_ttl_s: float = Field(default=10.0, gt=0.0)
    unitree_command_plan_history_size: int = Field(default=10, gt=0)
    unitree_execution_plan_ttl_s: float = Field(default=10.0, gt=0.0)
    unitree_execution_plan_history_size: int = Field(default=10, gt=0)
    unitree_execution_result_ttl_s: float = Field(default=10.0, gt=0.0)
    unitree_execution_result_history_size: int = Field(default=10, gt=0)
    rejected_command_ttl_s: float = Field(default=10.0, gt=0.0)
    rejected_command_history_size: int = Field(default=20, gt=0)

    safety_max_linear_mps: float = Field(default=0.35, gt=0.0)
    safety_max_angular_radps: float = Field(default=0.6, gt=0.0)
    safety_min_obstacle_distance_m: float = Field(default=0.5, ge=0.0)
    safety_state_ttl_s: float = Field(default=1.0, gt=0.0)
    safety_heartbeat_ttl_s: float = Field(default=2.0, gt=0.0)

    command_max_age_s: float = Field(default=1.0, gt=0.0)
    command_future_tolerance_s: float = Field(default=0.25, ge=0.0)
    command_max_commands_per_second: int = Field(default=20, gt=0)

    def unitree_config(self) -> UnitreeAdapterConfig:
        return UnitreeAdapterConfig(
            network_interface=self.unitree_network_interface,
            sdk_module=self.unitree_sdk_module,
            enable_motor_commands=self.unitree_enable_motor_commands,
            command_transport=self.unitree_command_transport,
        )

    def safety_limits(self) -> SafetyLimits:
        return SafetyLimits(
            max_linear_mps=self.safety_max_linear_mps,
            max_angular_radps=self.safety_max_angular_radps,
            min_obstacle_distance_m=self.safety_min_obstacle_distance_m,
            state_ttl_s=self.safety_state_ttl_s,
            heartbeat_ttl_s=self.safety_heartbeat_ttl_s,
        )

    def command_gate_limits(self) -> CommandGateLimits:
        return CommandGateLimits(
            max_age_s=self.command_max_age_s,
            future_tolerance_s=self.command_future_tolerance_s,
            max_commands_per_second=self.command_max_commands_per_second,
        )
