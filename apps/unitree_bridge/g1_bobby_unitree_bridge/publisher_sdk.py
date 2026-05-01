from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError
from g1_bobby_contracts import CommandEnvelope, CommandType, UnitreeCommandPlanRecord


@dataclass(frozen=True)
class SdkBindingIntent:
    command_type: str
    transport_surface: str
    binding_target: str
    binding_mode: str
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
        binding = resolve_sdk_binding(command)
        if binding is None:
            raise UnitreeTransportConfigurationError(
                f"Unitree SDK real publisher has no confirmed binding yet for command type: {command.type}"
            )
        raise UnitreeTransportConfigurationError(
            "Unitree SDK real publisher binding is identified but not implemented yet: "
            f"{binding.command_type} -> {binding.binding_target} [{binding.transport_surface}]"
        )
