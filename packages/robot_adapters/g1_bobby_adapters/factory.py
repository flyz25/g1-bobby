from __future__ import annotations

from .base import RobotAdapter
from .mock import MockRobotAdapter
from .unitree import UnitreeAdapter, UnitreeAdapterConfig


def create_robot_adapter(
    adapter_name: str,
    *,
    unitree_config: UnitreeAdapterConfig | None = None,
) -> RobotAdapter:
    normalized_name = adapter_name.lower()

    if normalized_name == "mock":
        return MockRobotAdapter()
    if normalized_name == "unitree":
        return UnitreeAdapter(config=unitree_config or UnitreeAdapterConfig())

    raise ValueError(f"unsupported robot adapter: {adapter_name}")
