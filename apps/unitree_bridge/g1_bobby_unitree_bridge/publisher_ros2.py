from __future__ import annotations

import json
from time import monotonic, time_ns
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
            binding_mode="g1_loco_request",
            note="G1 unitree_ros2 example g1_loco_client.hpp maps FSM changes to /api/sport/request with Request.header.identity.api_id=7101",
        )
    if command.type in {CommandType.MOVE_VELOCITY, CommandType.STOP}:
        return Ros2BindingIntent(
            command_type=str(command.type),
            topic="/api/sport/request",
            msg_type="unitree_api/msg/Request",
            binding_mode="g1_loco_request",
            note="G1 unitree_ros2 example g1_loco_client.hpp maps velocity changes to /api/sport/request with Request.header.identity.api_id=7105",
        )
    return None


def build_ros2_publish_plan(command: CommandEnvelope) -> Ros2PublishPlan | None:
    binding = resolve_ros2_binding(command)
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
                "ROS2 real publisher has no confirmed G1 loco FSM mapping for "
                f"set_mode={command.payload.mode}"
            )
        return Ros2PublishPlan(
            command_type=str(command.type),
            topic=binding.topic,
            msg_type=binding.msg_type,
            binding_mode=binding.binding_mode,
            payload={
                "api_id": 7101,
                "parameter": {"data": fsm_id},
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
                "api_id": 7105,
                "parameter": {
                    "velocity": [
                        command.payload.linear_x,
                        command.payload.linear_y,
                        command.payload.angular_z,
                    ],
                    "duration": command.payload.duration_ms / 1000.0,
                },
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
                "api_id": 7105,
                "parameter": {
                    "velocity": [0.0, 0.0, 0.0],
                    "duration": 1.0,
                },
            },
            note=binding.note,
        )

    return None


class Ros2RealUnitreeCommandPublisher:
    """Live ROS2 publisher for confirmed G1 sport request control."""

    def __init__(
        self,
        *,
        rclpy_module: str = "rclpy",
        request_module: str = "unitree_api.msg",
        request_class_name: str = "Request",
        response_module: str = "unitree_api.msg",
        response_class_name: str = "Response",
        response_timeout_s: float = 0.0,
    ) -> None:
        self._rclpy_module = rclpy_module
        self._request_module = request_module
        self._request_class_name = request_class_name
        self._response_module = response_module
        self._response_class_name = response_class_name
        self._response_timeout_s = response_timeout_s
        self._connected = False
        self._rclpy = None
        self._node = None
        self._sport_request_publisher = None
        self._sport_response_subscription = None
        self._request_class = None
        self._response_class = None
        self._pending_responses: dict[int, Any] = {}
        self._next_event_id = 1
        self._last_execution_plan: UnitreeExecutionPlan | None = None
        self._last_execution_result: UnitreeExecutionResult | None = None
        self._last_response: dict[str, Any] | None = None

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
        try:
            response_module = import_module(self._response_module)
            self._response_class = getattr(response_module, self._response_class_name)
        except ModuleNotFoundError as exc:
            if exc.name == self._response_module.split(".")[0]:
                raise UnitreeTransportConfigurationError(
                    f"ROS2 message module '{self._response_module}' is not installed"
                ) from exc
            raise
        except AttributeError as exc:
            raise UnitreeTransportConfigurationError(
                f"ROS2 message class '{self._response_class_name}' is not available in {self._response_module}"
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
        if hasattr(self._node, "create_subscription"):
            self._sport_response_subscription = self._node.create_subscription(
                self._response_class,
                "/api/sport/response",
                self._handle_response,
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
        self._sport_response_subscription = None
        self._node = None
        self._pending_responses.clear()
        self._connected = False

    def _handle_response(self, response: Any) -> None:
        identity = getattr(getattr(response, "header", None), "identity", None)
        response_id = getattr(identity, "id", None)
        if response_id is None:
            return
        self._pending_responses[int(response_id)] = response

    def _response_payload(self, response: Any) -> dict[str, Any]:
        header = getattr(response, "header", None)
        identity = getattr(header, "identity", None)
        status = getattr(header, "status", None)
        raw_data = getattr(response, "data", "")
        try:
            data = json.loads(raw_data) if raw_data else None
        except json.JSONDecodeError:
            data = raw_data
        return {
            "id": int(getattr(identity, "id", 0)),
            "api_id": int(getattr(identity, "api_id", 0)),
            "status_code": int(getattr(status, "code", 0)),
            "data": data,
        }

    def _wait_for_response(self, response_id: int) -> dict[str, Any] | None:
        if self._response_timeout_s <= 0:
            return None
        spin_once = getattr(self._rclpy, "spin_once", None)
        deadline = monotonic() + self._response_timeout_s
        while monotonic() < deadline:
            response = self._pending_responses.pop(response_id, None)
            if response is not None:
                return self._response_payload(response)
            if callable(spin_once) and self._node is not None:
                spin_once(self._node, timeout_sec=min(0.1, max(0.0, deadline - monotonic())))
            else:
                break
        response = self._pending_responses.pop(response_id, None)
        if response is not None:
            return self._response_payload(response)
        request_subscribers = None
        response_publishers = None
        if self._node is not None:
            count_subscribers = getattr(self._node, "count_subscribers", None)
            count_publishers = getattr(self._node, "count_publishers", None)
            if callable(count_subscribers):
                request_subscribers = count_subscribers("/api/sport/request")
            if callable(count_publishers):
                response_publishers = count_publishers("/api/sport/response")
        if request_subscribers == 0 and response_publishers == 0:
            raise UnitreeTransportConfigurationError(
                "timed out waiting for ROS2 sport response for request "
                f"id={response_id}; no remote ROS2 endpoints detected on "
                "/api/sport/request or /api/sport/response"
            )
        raise UnitreeTransportConfigurationError(
            f"timed out waiting for ROS2 sport response for request id={response_id}"
        )

    async def publish(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord:
        plan = build_ros2_publish_plan(command)
        if plan is None:
            raise UnitreeTransportConfigurationError(
                f"ROS2 real publisher has no confirmed binding yet for command type: {command.type}"
            )
        if not self._connected or self._sport_request_publisher is None or self._request_class is None:
            raise UnitreeTransportConfigurationError("ROS2 real publisher is not connected")
        if command.type not in {CommandType.SET_MODE, CommandType.MOVE_VELOCITY, CommandType.STOP}:
            raise UnitreeTransportConfigurationError(
                "ROS2 real publisher currently supports only confirmed G1 sport request control: "
                f"{plan.command_type} -> {plan.topic} ({plan.msg_type}) payload={asdict(plan)['payload']}"
            )

        request = self._request_class()
        try:
            request.header.identity.api_id = int(plan.payload["api_id"])
            request.header.identity.id = int(time_ns())
        except AttributeError as exc:
            raise UnitreeTransportConfigurationError(
                "ROS2 Request message does not expose header.identity.api_id/id"
            ) from exc
        setattr(request, "parameter", json.dumps(plan.payload["parameter"]))
        request_id = int(request.header.identity.id)
        self._sport_request_publisher.publish(request)
        response_payload = self._wait_for_response(request_id)
        self._last_response = response_payload

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
            status="responded" if response_payload is not None else "published",
            target=plan.topic,
            detail=(
                f"response code={response_payload['status_code']}"
                if response_payload is not None
                else "published G1 loco request over ROS2"
            ),
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

    def consume_last_response(self) -> dict[str, Any] | None:
        if self._last_response is None:
            return None
        response = dict(self._last_response)
        self._last_response = None
        return response
