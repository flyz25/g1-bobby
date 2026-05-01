from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import import_module
from typing import Any

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError
from g1_bobby_contracts import CommandEnvelope, CommandType, UnitreeCommandPlanRecord


@dataclass(frozen=True)
class SdkBindingIntent:
    command_type: str
    transport_surface: str
    binding_target: str
    binding_mode: str
    note: str


@dataclass(frozen=True)
class SdkPublishPlan:
    command_type: str
    transport_surface: str
    binding_target: str
    binding_mode: str
    payload: dict[str, Any]
    note: str


def resolve_sdk_binding(command: CommandEnvelope) -> SdkBindingIntent | None:
    if command.type == CommandType.SET_MODE:
        return SdkBindingIntent(
            command_type=str(command.type),
            transport_surface="request_response",
            binding_target="SportClient/basic service request",
            binding_mode="sport_service",
            note=(
                "Official unitree_sdk2_python high-level control uses sportmode_test.py and "
                "documents request-response control through sport services."
            ),
        )
    if command.type in {CommandType.MOVE_VELOCITY, CommandType.STOP}:
        return SdkBindingIntent(
            command_type=str(command.type),
            transport_surface="publish_subscribe",
            binding_target="rt/lowcmd (unitree_hg.msg.dds_.LowCmd_)",
            binding_mode="low_level_motor",
            note=(
                "Official unitree_sdk2_python low-level control documents topic publishing for "
                "motor control after sport_mode is disabled."
            ),
        )
    return None


def build_sdk_publish_plan(command: CommandEnvelope) -> SdkPublishPlan | None:
    binding = resolve_sdk_binding(command)
    if binding is None:
        return None

    if command.type == CommandType.SET_MODE:
        return SdkPublishPlan(
            command_type=str(command.type),
            transport_surface=binding.transport_surface,
            binding_target=binding.binding_target,
            binding_mode=binding.binding_mode,
            payload={
                "client": "SportClient",
                "operation": "switch_mode",
                "parameter": {"mode": command.payload.mode},
            },
            note=binding.note,
        )

    if command.type == CommandType.MOVE_VELOCITY:
        return SdkPublishPlan(
            command_type=str(command.type),
            transport_surface=binding.transport_surface,
            binding_target=binding.binding_target,
            binding_mode=binding.binding_mode,
            payload={
                "mode_pr": 0,
                "mode_machine": "low_level",
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
        return SdkPublishPlan(
            command_type=str(command.type),
            transport_surface=binding.transport_surface,
            binding_target=binding.binding_target,
            binding_mode=binding.binding_mode,
            payload={
                "mode_pr": 0,
                "mode_machine": "low_level",
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


class SdkRealUnitreeCommandPublisher:
    """Fail-closed skeleton for a future Unitree SDK/DDS command publisher."""

    def __init__(self, *, sdk_module: str = "unitree_sdk2py", network_interface: str | None = None) -> None:
        self._sdk_module = sdk_module
        self._network_interface = network_interface
        self._connected = False

    async def connect(self) -> None:
        if not self._network_interface:
            raise UnitreeTransportConfigurationError(
                "Unitree SDK publisher requires a network interface for DDS transport"
            )
        try:
            import_module(self._sdk_module)
        except ModuleNotFoundError as exc:
            if exc.name == self._sdk_module:
                raise UnitreeTransportConfigurationError(
                    f"Unitree SDK Python module '{self._sdk_module}' is not installed"
                ) from exc
            raise
        self._connected = True
        raise UnitreeTransportConfigurationError(
            "Unitree SDK/DDS publisher skeleton is available, but native DDS topic/service wiring "
            "for G1 command control is not implemented yet"
        )

    async def disconnect(self) -> None:
        self._connected = False

    async def publish(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord:
        plan = build_sdk_publish_plan(command)
        if plan is None:
            raise UnitreeTransportConfigurationError(
                f"Unitree SDK real publisher has no confirmed binding yet for command type: {command.type}"
            )
        raise UnitreeTransportConfigurationError(
            "Unitree SDK real publisher binding is identified but not implemented yet: "
            f"{plan.command_type} -> {plan.binding_target} [{plan.transport_surface}] payload={asdict(plan)['payload']}"
        )
