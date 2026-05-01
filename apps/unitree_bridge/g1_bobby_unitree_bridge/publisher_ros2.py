from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError
from g1_bobby_contracts import CommandEnvelope, CommandType, UnitreeCommandPlanRecord


@dataclass(frozen=True)
class Ros2BindingIntent:
    command_type: str
    topic: str
    msg_type: str
    binding_mode: str
    note: str


def resolve_ros2_binding(command: CommandEnvelope) -> Ros2BindingIntent | None:
    if command.type == CommandType.SET_MODE:
        return Ros2BindingIntent(
            command_type=str(command.type),
            topic="/api/sport/request",
            msg_type="unitree_api/msg/Request",
            binding_mode="sport_request",
            note="Requires SportClient-style request construction as shown in unitree_ros2 sport_mode_ctrl.cpp",
        )
    if command.type in {CommandType.MOVE_VELOCITY, CommandType.STOP}:
        return Ros2BindingIntent(
            command_type=str(command.type),
            topic="/lowcmd",
            msg_type="LowCmd",
            binding_mode="low_level_motor",
            note="Official unitree_ros2 README maps motor control to /lowcmd; exact package differs by robot family and G1 example path is g1/lowlevel/g1_low_level_example",
        )
    return None


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
        binding = resolve_ros2_binding(command)
        if binding is None:
            raise UnitreeTransportConfigurationError(
                f"ROS2 real publisher has no confirmed binding yet for command type: {command.type}"
            )
        raise UnitreeTransportConfigurationError(
            "ROS2 real publisher binding is identified but not implemented yet: "
            f"{binding.command_type} -> {binding.topic} ({binding.msg_type})"
        )
