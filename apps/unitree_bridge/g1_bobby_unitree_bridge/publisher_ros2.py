from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import import_module
from typing import Any

from g1_bobby_adapters.unitree_transport import (
    UnitreeTransportConfigurationError,
    build_unitree_command_plan_record,
)
from g1_bobby_contracts import (
    CommandEnvelope,
    CommandType,
    UnitreeCommandPlanRecord,
    UnitreeExecutionPlan,
    UnitreeExecutionResult,
)


@dataclass(frozen=True)
class Ros2BindingIntent:
    command_type: str
    topic: str
    msg_type: str
    binding_mode: str
    note: str


@dataclass(frozen=True)
class Ros2PublishPlan:
    command_type: str
    topic: str
    msg_type: str
    binding_mode: str
    payload: dict[str, Any]
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


def build_ros2_publish_plan(command: CommandEnvelope) -> Ros2PublishPlan | None:
    binding = resolve_ros2_binding(command)
    if binding is None:
        return None

    if command.type == CommandType.SET_MODE:
        return Ros2PublishPlan(
            command_type=str(command.type),
            topic=binding.topic,
            msg_type=binding.msg_type,
            binding_mode=binding.binding_mode,
            payload={
                "api_id": "switch_mode",
                "parameter": {"mode": command.payload.mode},
            },
            note=binding.note,
        )

    if command.type == CommandType.MOVE_VELOCITY:
        return Ros2PublishPlan(
            command_type=str(command.type),
            topic=binding.topic,
            msg_type=binding.msg_type,
            binding_mode=binding.binding_mode,
            payload={
                "mode": "velocity",
                "velocity": {
                    "linear_x": command.payload.linear_x,
                    "linear_y": command.payload.linear_y,
                    "angular_z": command.payload.angular_z,
                },
                "duration_ms": command.payload.duration_ms,
            },
            note=binding.note,
        )

    if command.type == CommandType.STOP:
        return Ros2PublishPlan(
            command_type=str(command.type),
            topic=binding.topic,
            msg_type=binding.msg_type,
            binding_mode=binding.binding_mode,
            payload={
                "mode": "velocity",
                "velocity": {
                    "linear_x": 0.0,
                    "linear_y": 0.0,
                    "angular_z": 0.0,
                },
                "reason": command.payload.reason,
            },
            note=binding.note,
        )

    return None


class Ros2RealUnitreeCommandPublisher:
    """Partial live ROS2 publisher for confirmed sport-request control only."""

    def __init__(
        self,
        *,
        rclpy_module: str = "rclpy",
        request_module: str = "unitree_api.msg",
        request_class_name: str = "Request",
    ) -> None:
        self._rclpy_module = rclpy_module
        self._request_module = request_module
        self._request_class_name = request_class_name
        self._connected = False
        self._rclpy = None
        self._node = None
        self._sport_request_publisher = None
        self._request_class = None
        self._next_event_id = 1
        self._last_execution_plan: UnitreeExecutionPlan | None = None
        self._last_execution_result: UnitreeExecutionResult | None = None

    async def connect(self) -> None:
        try:
            self._rclpy = import_module(self._rclpy_module)
        except ModuleNotFoundError as exc:
            if exc.name == self._rclpy_module:
                raise UnitreeTransportConfigurationError(
                    f"ROS2 Python module '{self._rclpy_module}' is not installed"
                ) from exc
            raise
        try:
            request_module = import_module(self._request_module)
            self._request_class = getattr(request_module, self._request_class_name)
        except ModuleNotFoundError as exc:
            if exc.name == self._request_module.split(".")[0]:
                raise UnitreeTransportConfigurationError(
                    f"ROS2 message module '{self._request_module}' is not installed"
                ) from exc
            raise
        except AttributeError as exc:
            raise UnitreeTransportConfigurationError(
                f"ROS2 message class '{self._request_class_name}' is not available in {self._request_module}"
            ) from exc
        if not hasattr(self._rclpy, "create_node"):
            raise UnitreeTransportConfigurationError(
                "ROS2 Python module is present but does not expose create_node"
            )
        init_fn = getattr(self._rclpy, "init", None)
        ok_fn = getattr(self._rclpy, "ok", None)
        if callable(init_fn) and (not callable(ok_fn) or not ok_fn()):
            init_fn(args=None)
        self._node = self._rclpy.create_node("g1_bobby_unitree_ros2_bridge")
        if not hasattr(self._node, "create_publisher"):
            raise UnitreeTransportConfigurationError(
                "ROS2 node does not expose create_publisher for sport request control"
            )
        self._sport_request_publisher = self._node.create_publisher(
            self._request_class,
            "/api/sport/request",
            10,
        )
        self._connected = True

    async def disconnect(self) -> None:
        if self._node is not None and hasattr(self._node, "destroy_node"):
            self._node.destroy_node()
        shutdown_fn = getattr(self._rclpy, "shutdown", None)
        ok_fn = getattr(self._rclpy, "ok", None)
        if callable(shutdown_fn) and (not callable(ok_fn) or ok_fn()):
            shutdown_fn()
        self._sport_request_publisher = None
        self._node = None
        self._connected = False

    async def publish(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord:
        plan = build_ros2_publish_plan(command)
        if plan is None:
            raise UnitreeTransportConfigurationError(
                f"ROS2 real publisher has no confirmed binding yet for command type: {command.type}"
            )
        if not self._connected or self._sport_request_publisher is None or self._request_class is None:
            raise UnitreeTransportConfigurationError("ROS2 real publisher is not connected")
        if command.type != CommandType.SET_MODE:
            raise UnitreeTransportConfigurationError(
                "ROS2 real publisher currently supports only sport request control: "
                f"{plan.command_type} -> {plan.topic} ({plan.msg_type}) payload={asdict(plan)['payload']}"
            )

        request = self._request_class()
        setattr(request, "api_id", plan.payload["api_id"])
        setattr(request, "parameter", plan.payload["parameter"])
        self._sport_request_publisher.publish(request)

        self._last_execution_plan = UnitreeExecutionPlan(
            transport="ros2_real",
            command_type=plan.command_type,
            binding_mode=plan.binding_mode,
            surface=plan.msg_type,
            target=plan.topic,
            payload=dict(plan.payload),
            note=plan.note,
        )
        self._last_execution_result = UnitreeExecutionResult(
            transport="ros2_real",
            command_type=plan.command_type,
            status="published",
            target=plan.topic,
            detail="published sport request message over ROS2",
        )
        record = build_unitree_command_plan_record(
            command,
            event_id=self._next_event_id,
            transport="ros2_real",
        )
        self._next_event_id += 1
        return record

    def consume_last_execution_plan(self) -> UnitreeExecutionPlan | None:
        if self._last_execution_plan is None:
            return None
        plan = self._last_execution_plan.model_copy(deep=True)
        self._last_execution_plan = None
        return plan

    def consume_last_execution_result(self) -> UnitreeExecutionResult | None:
        if self._last_execution_result is None:
            return None
        result = self._last_execution_result.model_copy(deep=True)
        self._last_execution_result = None
        return result
