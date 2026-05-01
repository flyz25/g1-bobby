from __future__ import annotations

from importlib import import_module

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError
from g1_bobby_contracts import CommandEnvelope, UnitreeCommandPlanRecord


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
        raise UnitreeTransportConfigurationError(
            f"Unitree SDK real publisher is not implemented for command transport: {command.type}"
        )
