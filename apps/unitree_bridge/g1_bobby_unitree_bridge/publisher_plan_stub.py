from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from g1_bobby_contracts import (
    CommandEnvelope,
    UnitreeCommandPlanRecord,
    UnitreeExecutionPlan,
    UnitreeExecutionResult,
)
from pydantic import TypeAdapter

from g1_bobby_adapters.unitree_transport import (
    UnitreeTransportConfigurationError,
    build_unitree_command_plan_record,
)
from g1_bobby_unitree_bridge.publisher_ros2 import Ros2PublishPlan, build_ros2_publish_plan
from g1_bobby_unitree_bridge.publisher_sdk import SdkPublishPlan, build_sdk_publish_plan

class PlanStubUnitreeCommandPublisher:
    def __init__(self, *, transport: str) -> None:
        if transport not in {"ros2_plan_stub", "sdk_plan_stub"}:
            raise ValueError(f"unsupported plan stub transport: {transport}")
        self._transport = transport
        self._next_event_id = 1
        self._published: list[UnitreeCommandPlanRecord] = []
        self._emitted: list[UnitreeExecutionPlan] = []
        self._results: list[UnitreeExecutionResult] = []

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def publish(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord:
        plan = self._build_plan(command)
        if plan is None:
            raise UnitreeTransportConfigurationError(
                f"{self._transport} has no confirmed publish-plan binding for command type: {command.type}"
            )

        record = build_unitree_command_plan_record(
            command,
            event_id=self._next_event_id,
            transport=self._transport,
        )
        self._next_event_id += 1
        self._published.append(record)
        execution_plan = _normalize_execution_plan(self._transport, plan.__dict__)
        self._emitted.append(execution_plan)
        self._results.append(
            UnitreeExecutionResult(
                transport=self._transport,
                command_type=execution_plan.command_type,
                status="stub_emitted",
                target=execution_plan.target,
                detail="publish-plan stub emitted the normalized execution plan without live transport",
            )
        )
        return record

    def published_records(self) -> list[UnitreeCommandPlanRecord]:
        return [record.model_copy(deep=True) for record in self._published]

    def emitted_plans(self) -> list[UnitreeExecutionPlan]:
        return [item.model_copy(deep=True) for item in self._emitted]

    def consume_last_execution_plan(self) -> UnitreeExecutionPlan | None:
        if not self._emitted:
            return None
        return self._emitted[-1].model_copy(deep=True)

    def consume_last_execution_result(self) -> UnitreeExecutionResult | None:
        if not self._results:
            return None
        return self._results[-1].model_copy(deep=True)

    def _build_plan(self, command: CommandEnvelope) -> Ros2PublishPlan | SdkPublishPlan | None:
        if self._transport == "ros2_plan_stub":
            return build_ros2_publish_plan(command)
        return build_sdk_publish_plan(command)


def _normalize_execution_plan(transport: str, plan: dict[str, Any]) -> UnitreeExecutionPlan:
    if "topic" in plan and "msg_type" in plan:
        return UnitreeExecutionPlan(
            transport=transport,
            command_type=str(plan["command_type"]),
            binding_mode=str(plan["binding_mode"]),
            surface=str(plan["msg_type"]),
            target=str(plan["topic"]),
            payload=dict(plan["payload"]),
            note=str(plan["note"]),
        )
    return UnitreeExecutionPlan(
        transport=transport,
        command_type=str(plan["command_type"]),
        binding_mode=str(plan["binding_mode"]),
        surface=str(plan["transport_surface"]),
        target=str(plan["binding_target"]),
        payload=dict(plan["payload"]),
        note=str(plan["note"]),
    )


command_adapter = TypeAdapter(CommandEnvelope)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute commands through Unitree publish-plan stubs without live transport."
    )
    parser.add_argument(
        "--transport",
        choices=("ros2_plan_stub", "sdk_plan_stub"),
        required=True,
        help="Plan-backed stub transport to execute.",
    )
    parser.add_argument("--command-json", help="Single command JSON object")
    parser.add_argument("--script", type=Path, help="JSONL command script")
    return parser


def _load_commands(args: argparse.Namespace) -> list[CommandEnvelope]:
    raw_messages: list[dict[str, Any]] = []
    if args.command_json:
        raw_messages.append(json.loads(args.command_json))
    if args.script:
        for line in args.script.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                raw_messages.append(json.loads(stripped))
    if not raw_messages:
        raise ValueError("provide --command-json or --script")
    return [command_adapter.validate_python(message) for message in raw_messages]


async def _run_publish(args: argparse.Namespace) -> dict[str, Any]:
    publisher = PlanStubUnitreeCommandPublisher(transport=args.transport)
    await publisher.connect()
    try:
        records = [await publisher.publish(command) for command in _load_commands(args)]
        emitted = publisher.emitted_plans()
    finally:
        await publisher.disconnect()
    return {
        "records": [record.model_dump(mode="json") for record in records],
        "emitted_plans": [item.model_dump(mode="json") for item in emitted],
        "execution_results": [item.model_dump(mode="json") for item in publisher._results],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        import asyncio

        payload = asyncio.run(_run_publish(args))
    except (ValueError, json.JSONDecodeError, UnitreeTransportConfigurationError) as exc:
        print(f"unitree plan stub publish failed: {exc}")
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
