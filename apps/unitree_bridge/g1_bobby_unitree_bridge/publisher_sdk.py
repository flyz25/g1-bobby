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
            binding_target="unitree_sdk2py.g1.loco.LocoClient.SetFsmId",
            binding_mode="g1_loco_service",
            note=(
                "Official unitree_sdk2py exposes G1 high-level locomotion through "
                "unitree_sdk2py.g1.loco.g1_loco_client.LocoClient."
            ),
        )
    if command.type in {CommandType.MOVE_VELOCITY, CommandType.STOP}:
        return SdkBindingIntent(
            command_type=str(command.type),
            transport_surface="request_response",
            binding_target="unitree_sdk2py.g1.loco.LocoClient.SetVelocity",
            binding_mode="g1_loco_service",
            note=(
                "Official unitree_sdk2py G1 loco client exposes base velocity through "
                "SetVelocity(vx, vy, omega, duration)."
            ),
        )
    return None


def build_sdk_publish_plan(command: CommandEnvelope) -> SdkPublishPlan | None:
    binding = resolve_sdk_binding(command)
    if binding is None:
        return None

    if command.type == CommandType.SET_MODE:
        fsm_id_by_mode = {
            "idle": 1,
            "manual": 500,
        }
        fsm_id = fsm_id_by_mode.get(command.payload.mode)
        if fsm_id is None:
            raise UnitreeTransportConfigurationError(
                "Unitree SDK real publisher has no confirmed G1 loco FSM mapping for "
                f"set_mode={command.payload.mode}"
            )
        return SdkPublishPlan(
            command_type=str(command.type),
            transport_surface=binding.transport_surface,
            binding_target=binding.binding_target,
            binding_mode=binding.binding_mode,
            payload={
                "operation": "SetFsmId",
                "fsm_id": fsm_id,
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
                "operation": "SetVelocity",
                "velocity": {
                    "linear_x": command.payload.linear_x,
                    "linear_y": command.payload.linear_y,
                    "angular_z": command.payload.angular_z,
                },
                "duration_s": command.payload.duration_ms / 1000.0,
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
                "operation": "SetVelocity",
                "velocity": {
                    "linear_x": 0.0,
                    "linear_y": 0.0,
                    "angular_z": 0.0,
                },
                "duration_s": 1.0,
                "reason": command.payload.reason,
            },
            note=binding.note,
        )

    return None


class SdkRealUnitreeCommandPublisher:
    """Live Unitree SDK publisher backed by unitree_sdk2py G1 loco client."""

    def __init__(
        self,
        *,
        sdk_module: str = "unitree_sdk2py",
        network_interface: str | None = None,
        timeout_s: float = 2.0,
        channel_module: str = "unitree_sdk2py.core.channel",
        loco_client_module: str = "unitree_sdk2py.g1.loco.g1_loco_client",
        loco_client_class_name: str = "LocoClient",
    ) -> None:
        self._sdk_module = sdk_module
        self._network_interface = network_interface
        self._timeout_s = timeout_s
        self._channel_module = channel_module
        self._loco_client_module = loco_client_module
        self._loco_client_class_name = loco_client_class_name
        self._connected = False
        self._channel_factory_initialize = None
        self._loco_client = None
        self._next_event_id = 1
        self._last_execution_plan: UnitreeExecutionPlan | None = None
        self._last_execution_result: UnitreeExecutionResult | None = None
        self._last_response: dict[str, Any] | None = None

    @staticmethod
    def _status_label(status_code: int) -> str:
        labels = {
            0: "RPC_OK",
            3001: "RPC_ERR_UNKNOWN",
            3102: "RPC_ERR_CLIENT_SEND",
            3103: "RPC_ERR_CLIENT_API_NOT_REG",
            3104: "RPC_ERR_CLIENT_API_TIMEOUT",
            3105: "RPC_ERR_CLIENT_API_NOT_MATCH",
            3106: "RPC_ERR_CLIENT_API_DATA",
            3107: "RPC_ERR_CLIENT_LEASE_INVALID",
            3201: "RPC_ERR_SERVER_SEND",
            3202: "RPC_ERR_SERVER_INTERNAL",
            3203: "RPC_ERR_SERVER_API_NOT_IMPL",
            3204: "RPC_ERR_SERVER_API_PARAMETER",
            3205: "RPC_ERR_SERVER_LEASE_DENIED",
            3206: "RPC_ERR_SERVER_LEASE_NOT_EXIST",
            3207: "RPC_ERR_SERVER_LEASE_EXIST",
        }
        return labels.get(status_code, "UNKNOWN_STATUS")

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

        try:
            channel_module = import_module(self._channel_module)
            self._channel_factory_initialize = getattr(channel_module, "ChannelFactoryInitialize")
        except (ModuleNotFoundError, AttributeError) as exc:
            raise UnitreeTransportConfigurationError(
                f"Unitree SDK channel factory is not available in {self._channel_module}"
            ) from exc

        try:
            loco_module = import_module(self._loco_client_module)
            loco_client_class = getattr(loco_module, self._loco_client_class_name)
        except (ModuleNotFoundError, AttributeError) as exc:
            raise UnitreeTransportConfigurationError(
                f"Unitree SDK G1 loco client is not available in {self._loco_client_module}"
            ) from exc

        self._channel_factory_initialize(0, self._network_interface)
        self._loco_client = loco_client_class()
        if hasattr(self._loco_client, "SetTimeout"):
            self._loco_client.SetTimeout(self._timeout_s)
        if not hasattr(self._loco_client, "Init"):
            raise UnitreeTransportConfigurationError("Unitree SDK G1 loco client does not expose Init()")
        self._loco_client.Init()
        self._connected = True

    async def disconnect(self) -> None:
        self._loco_client = None
        self._connected = False

    def _call_loco(self, plan: SdkPublishPlan) -> int:
        if self._loco_client is None:
            raise UnitreeTransportConfigurationError("Unitree SDK real publisher is not connected")
        if plan.payload["operation"] == "SetFsmId":
            return int(self._loco_client.SetFsmId(int(plan.payload["fsm_id"])))
        if plan.payload["operation"] == "SetVelocity":
            velocity = plan.payload["velocity"]
            return int(
                self._loco_client.SetVelocity(
                    float(velocity["linear_x"]),
                    float(velocity["linear_y"]),
                    float(velocity["angular_z"]),
                    float(plan.payload["duration_s"]),
                )
            )
        raise UnitreeTransportConfigurationError(
            f"unsupported Unitree SDK loco operation: {plan.payload['operation']}"
        )

    async def publish(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord:
        plan = build_sdk_publish_plan(command)
        if plan is None:
            raise UnitreeTransportConfigurationError(
                f"Unitree SDK real publisher has no confirmed binding yet for command type: {command.type}"
            )
        if not self._connected or self._loco_client is None:
            raise UnitreeTransportConfigurationError("Unitree SDK real publisher is not connected")

        status_code = self._call_loco(plan)
        self._last_response = {
            "status_code": status_code,
            "status_label": self._status_label(status_code),
            "operation": plan.payload["operation"],
        }
        self._last_execution_plan = UnitreeExecutionPlan(
            transport="sdk_real",
            command_type=plan.command_type,
            binding_mode=plan.binding_mode,
            surface=plan.transport_surface,
            target=plan.binding_target,
            payload=dict(plan.payload),
            note=plan.note,
        )
        self._last_execution_result = UnitreeExecutionResult(
            transport="sdk_real",
            command_type=plan.command_type,
            status="responded" if status_code == 0 else "failed",
            target=plan.binding_target,
            detail=f"sdk status_code={status_code} ({self._status_label(status_code)})",
        )
        if status_code != 0:
            raise UnitreeTransportConfigurationError(
                "Unitree SDK G1 loco client returned non-zero status: "
                f"{plan.command_type} -> {plan.binding_target} [{plan.transport_surface}] "
                f"status_code={status_code} ({self._status_label(status_code)}) "
                f"payload={asdict(plan)['payload']}"
            )

        record = build_unitree_command_plan_record(
            command,
            event_id=self._next_event_id,
            transport="sdk_real",
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

    def consume_last_response(self) -> dict[str, Any] | None:
        if self._last_response is None:
            return None
        response = dict(self._last_response)
        self._last_response = None
        return response
