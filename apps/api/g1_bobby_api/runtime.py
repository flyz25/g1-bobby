from __future__ import annotations

from dataclasses import dataclass

from g1_bobby_adapters import RobotAdapter, create_robot_adapter
from g1_bobby_safety import SafetyValidator

from .config import Settings


@dataclass
class Runtime:
    adapter: RobotAdapter
    safety: SafetyValidator
    adapter_name: str
    rejected_commands: int = 0

    @classmethod
    async def create(cls, settings: Settings | None = None) -> "Runtime":
        resolved_settings = settings or Settings()
        adapter = create_robot_adapter(
            str(resolved_settings.robot_adapter),
            unitree_config=resolved_settings.unitree_config(),
        )
        await adapter.connect()
        return cls(
            adapter=adapter,
            safety=SafetyValidator(resolved_settings.safety_limits()),
            adapter_name=str(resolved_settings.robot_adapter),
        )
