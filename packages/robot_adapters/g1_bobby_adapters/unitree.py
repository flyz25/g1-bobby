from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from time import time
from typing import Mapping

from g1_bobby_contracts.commands import CommandEnvelope
from g1_bobby_contracts.unitree_command import (
    UnitreeExecutionPlan,
    UnitreeExecutionResult,
    UnitreeTransportCapability,
)
from g1_bobby_contracts.state import ControlMode, RobotState

from .unitree_transport import (
    DisabledUnitreeCommandPublisher,
    DryRunUnitreeCommandPublisher,
    UnitreeCommandPublisher,
    UnitreeTransportConfigurationError,
)


class UnitreeAdapterError(RuntimeError):
    """Base error for the Unitree adapter boundary."""


class UnitreeAdapterConfigurationError(UnitreeAdapterError):
    """Raised when the Unitree adapter is selected without required wiring."""


@dataclass(frozen=True)
class UnitreeAdapterConfig:
    network_interface: str | None = None
    sdk_module: str = "unitree_sdk2py"
    enable_motor_commands: bool = False
    command_transport: str = "disabled"


TRANSPORT_SUPPORTED_COMMAND_TYPES: dict[str, list[str]] = {
    "disabled": ["heartbeat", "set_mode", "move_velocity", "stop", "estop"],
    "dry_run": ["heartbeat", "set_mode", "move_velocity", "stop", "estop"],
    "ros2_stub": ["heartbeat", "set_mode", "move_velocity", "stop", "estop"],
    "ros2_plan_stub": ["set_mode", "move_velocity", "stop"],
    "ros2_real": ["set_mode", "move_velocity", "stop"],
    "sdk_plan_stub": ["set_mode", "move_velocity", "stop"],
    "sdk_real": ["set_mode", "move_velocity", "stop"],
}


def describe_unitree_transport_capability(
    config: UnitreeAdapterConfig,
    *,
    env: Mapping[str, str] | None = None,
) -> UnitreeTransportCapability:
    transport = config.command_transport.lower()
    probe_module = import_module("g1_bobby_unitree_bridge.probe")
    checks = probe_module.build_probe_status(
        env,
        network_interface=config.network_interface,
        sdk_module=config.sdk_module,
    )
    dependency_blockers: list[str] = []
    if not config.network_interface:
        dependency_blockers.append("G1_BOBBY_UNITREE_NETWORK_INTERFACE is not set")
    if not checks.get("unitree_sdk_available"):
        dependency_blockers.append(f"{config.sdk_module} is not importable")
    if transport == "ros2_real":
        if checks.get("ros_distro") != "humble":
            dependency_blockers.append("ROS_DISTRO is not humble")
        if checks.get("rmw_implementation") != "rmw_cyclonedds_cpp":
            dependency_blockers.append("RMW_IMPLEMENTATION is not rmw_cyclonedds_cpp")
        if not checks.get("rclpy_available"):
            dependency_blockers.append("rclpy is not importable")
        if not checks.get("unitree_api_request_available"):
            dependency_blockers.append("unitree_api.msg is not importable")

    if transport == "disabled":
        binding_implemented = False
        implementation_blocker = "Unitree command transport is disabled"
    elif transport in {"ros2_real", "sdk_real"}:
        binding_implemented = True
        implementation_blocker = None
    else:
        binding_implemented = True
        implementation_blocker = None

    blockers = list(dependency_blockers)
    if not config.enable_motor_commands:
        blockers.append("G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS is false")
    if implementation_blocker is not None:
        blockers.append(implementation_blocker)

    environment_ready = not dependency_blockers
    ready = environment_ready and config.enable_motor_commands and binding_implemented
    return UnitreeTransportCapability(
        transport=transport,
        supported_command_types=TRANSPORT_SUPPORTED_COMMAND_TYPES.get(transport, []),
        configured=bool(config.network_interface),
        environment_ready=environment_ready,
        execution_enabled=config.enable_motor_commands,
        binding_implemented=binding_implemented,
        ready=ready,
        blockers=blockers,
        checks=dict(checks),
    )


class UnitreeAdapter:
    """Fail-closed boundary for the real Unitree SDK/ROS2 adapter.

    This class validates the runtime wiring needed for a future hardware
    adapter. It intentionally does not send motor commands until a concrete
    Unitree SDK or ROS2 transport binding is implemented and reviewed.
    """

    def __init__(
        self,
        config: UnitreeAdapterConfig | None = None,
        *,
        publisher: UnitreeCommandPublisher | None = None,
    ) -> None:
        self.config = config or UnitreeAdapterConfig()
        self._publisher = publisher or self._create_publisher(self.config.command_transport)
        self._last_execution_plan: UnitreeExecutionPlan | None = None
        self._last_execution_result: UnitreeExecutionResult | None = None
        self._state = RobotState(
            connected=False,
            estop_engaged=True,
            mode=ControlMode.IDLE,
            battery_percent=0.0,
            obstacle_distance_m=None,
            last_state_at=time(),
            last_heartbeat_at=None,
            pose_label="unitree-disconnected",
        )

    def _create_publisher(self, transport: str) -> UnitreeCommandPublisher:
        normalized = transport.lower()
        if normalized == "disabled":
            return DisabledUnitreeCommandPublisher()
        if normalized == "dry_run":
            return DryRunUnitreeCommandPublisher()
        if normalized == "ros2_stub":
            module = import_module("g1_bobby_unitree_bridge.publisher_stub")
            return module.Ros2StubUnitreeCommandPublisher()
        if normalized == "ros2_plan_stub":
            module = import_module("g1_bobby_unitree_bridge.publisher_plan_stub")
            return module.PlanStubUnitreeCommandPublisher(transport="ros2_plan_stub")
        if normalized == "ros2_real":
            module = import_module("g1_bobby_unitree_bridge.publisher_ros2")
            return module.Ros2RealUnitreeCommandPublisher()
        if normalized == "sdk_plan_stub":
            module = import_module("g1_bobby_unitree_bridge.publisher_plan_stub")
            return module.PlanStubUnitreeCommandPublisher(transport="sdk_plan_stub")
        if normalized == "sdk_real":
            module = import_module("g1_bobby_unitree_bridge.publisher_sdk")
            return module.SdkRealUnitreeCommandPublisher(
                sdk_module=self.config.sdk_module,
                network_interface=self.config.network_interface,
            )
        raise UnitreeAdapterConfigurationError(f"unsupported Unitree command transport: {transport}")

    def _infer_blocked_target(self, command: CommandEnvelope) -> str:
        transport = self.config.command_transport.lower()
        if transport == "ros2_real":
            module = import_module("g1_bobby_unitree_bridge.publisher_ros2")
            plan = module.build_ros2_publish_plan(command)
            if plan is not None:
                return str(plan.topic)
        if transport == "sdk_real":
            module = import_module("g1_bobby_unitree_bridge.publisher_sdk")
            plan = module.build_sdk_publish_plan(command)
            if plan is not None:
                return str(plan.binding_target)
        return transport

    def _set_blocked_execution_result(self, command: CommandEnvelope, detail: str) -> None:
        self._last_execution_result = UnitreeExecutionResult(
            transport=self.config.command_transport.lower(),
            command_type=str(command.type),
            status="blocked",
            target=self._infer_blocked_target(command),
            detail=detail,
        )

    async def connect(self) -> None:
        if not self.config.network_interface:
            raise UnitreeAdapterConfigurationError(
                "G1_BOBBY_UNITREE_NETWORK_INTERFACE is required when "
                "G1_BOBBY_ROBOT_ADAPTER=unitree"
            )

        try:
            import_module(self.config.sdk_module)
        except ModuleNotFoundError as exc:
            if exc.name == self.config.sdk_module:
                raise UnitreeAdapterConfigurationError(
                    f"Unitree SDK module '{self.config.sdk_module}' is not installed"
                ) from exc
            raise
        try:
            await self._publisher.connect()
        except UnitreeTransportConfigurationError as exc:
            raise UnitreeAdapterConfigurationError(str(exc)) from exc
        self._state.connected = True
        self._state.estop_engaged = False
        self._state.mode = ControlMode.IDLE
        self._state.pose_label = f"unitree-{self.config.command_transport}"
        self._state.last_state_at = time()

    async def disconnect(self) -> None:
        await self._publisher.disconnect()
        self._state.connected = False
        self._state.estop_engaged = True
        self._state.mode = ControlMode.IDLE
        self._state.pose_label = "unitree-disconnected"
        self._state.last_state_at = time()

    async def get_state(self) -> RobotState:
        self._state.last_state_at = time()
        return self._state.model_copy()

    async def execute(self, command: CommandEnvelope) -> None:
        if not self.config.enable_motor_commands:
            detail = f"motor command execution is disabled for Unitree adapter: {command.type}"
            self._set_blocked_execution_result(command, detail)
            raise UnitreeAdapterConfigurationError(detail)
        try:
            await self._publisher.publish(command)
        except UnitreeTransportConfigurationError as exc:
            self._set_blocked_execution_result(command, str(exc))
            raise UnitreeAdapterConfigurationError(str(exc)) from exc
        self._last_execution_plan = None
        self._last_execution_result = None
        consume_execution_plan = getattr(self._publisher, "consume_last_execution_plan", None)
        if callable(consume_execution_plan):
            self._last_execution_plan = consume_execution_plan()
        consume_execution_result = getattr(self._publisher, "consume_last_execution_result", None)
        if callable(consume_execution_result):
            self._last_execution_result = consume_execution_result()

        if str(command.type) == "heartbeat":
            self._state.last_heartbeat_at = command.timestamp
        elif str(command.type) == "set_mode":
            self._state.mode = ControlMode(command.payload.mode)
        elif str(command.type) == "stop":
            self._state.mode = ControlMode.IDLE
        self._state.last_state_at = time()

    async def emergency_stop(self) -> None:
        self._state.estop_engaged = True
        self._state.mode = ControlMode.IDLE
        self._state.last_state_at = time()

    async def reset_emergency_stop(self) -> bool:
        if not self._state.connected:
            return False
        self._state.estop_engaged = False
        self._state.mode = ControlMode.IDLE
        self._state.last_state_at = time()
        return True

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

    def transport_capability(self) -> UnitreeTransportCapability:
        return describe_unitree_transport_capability(self.config)
