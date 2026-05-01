from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from g1_bobby_contracts import CommandEnvelope, UnitreeCommandPlanRecord
from pydantic import TypeAdapter

from g1_bobby_adapters.unitree_transport import build_unitree_command_plan_record


class Ros2StubUnitreeCommandPublisher:
    """Bridge-side publisher stub that models a future ROS2 command publisher."""

    def __init__(self) -> None:
        self._next_event_id = 1
        self._published: list[UnitreeCommandPlanRecord] = []

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def publish(self, command: CommandEnvelope) -> UnitreeCommandPlanRecord:
        record = build_unitree_command_plan_record(
            command,
            event_id=self._next_event_id,
            transport="ros2_stub",
        )
        self._next_event_id += 1
        self._published.append(record)
        return record

    def published_records(self) -> list[UnitreeCommandPlanRecord]:
        return [record.model_copy(deep=True) for record in self._published]


command_adapter = TypeAdapter(CommandEnvelope)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish a command through the Unitree ROS2 stub publisher.")
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


async def _run_publish(args: argparse.Namespace) -> list[dict[str, Any]]:
    publisher = Ros2StubUnitreeCommandPublisher()
    await publisher.connect()
    try:
        records = [await publisher.publish(command) for command in _load_commands(args)]
    finally:
        await publisher.disconnect()
    return [record.model_dump(mode="json") for record in records]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        import asyncio

        records = asyncio.run(_run_publish(args))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"unitree ros2 stub publish failed: {exc}")
        return 1
    print(json.dumps({"records": records}, indent=2, sort_keys=True))
    return 0
