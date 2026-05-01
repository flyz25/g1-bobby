from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from time import time

from g1_bobby_contracts.commands import CommandEnvelope
from g1_bobby_contracts.unitree_command import UnitreeExecutionPlan, UnitreeExecutionResult
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
            raise UnitreeAdapterConfigurationError(
                f"motor command execution is disabled for Unitree adapter: {command.type}"
            )
        try:
            await self._publisher.publish(command)
        except UnitreeTransportConfigurationError as exc:
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
