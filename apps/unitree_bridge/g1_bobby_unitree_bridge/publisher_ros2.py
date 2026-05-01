from __future__ import annotations

from importlib import import_module

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError
from g1_bobby_contracts import CommandEnvelope, UnitreeCommandPlanRecord


class Ros2RealUnitreeCommandPublisher:
    """Fail-closed skeleton for a future real ROS2 command publisher."""

    def __init__(self, *, rclpy_module: str = "rclpy") -> None:
        self._rclpy_module = rclpy_module
        self._connected = False

    async def connect(self) -> None:
        try:
            import_module(self._rclpy_module)
        except ModuleNotFoundError as exc:
            if exc.name == self._rclpy_module:
                raise UnitreeTransportConfigurationError(
                    f"ROS2 Python module '{self._rclpy_module}' is not installed"
                ) from exc
            raise
        self._connected = True
        raise UnitreeTransportConfigurationError(
            "ROS2 command publisher skeleton is available, but native ROS2 topic/action wiring "
            "is not implemented yet"
        )

    async def disconnect(self) -> None:
        self._connected = False

    async def publish(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord:
        raise UnitreeTransportConfigurationError(
            f"ROS2 real publisher is not implemented for command transport: {command.type}"
        )
