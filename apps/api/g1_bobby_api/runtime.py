from __future__ import annotations

from dataclasses import dataclass

from g1_bobby_adapters import MockRobotAdapter
from g1_bobby_safety import SafetyValidator


@dataclass
class Runtime:
    adapter: MockRobotAdapter
    safety: SafetyValidator
    rejected_commands: int = 0

    @classmethod
    async def create(cls) -> "Runtime":
        adapter = MockRobotAdapter()
        await adapter.connect()
        return cls(adapter=adapter, safety=SafetyValidator())

