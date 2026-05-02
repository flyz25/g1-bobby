from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from pydantic import TypeAdapter, ValidationError

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError
from g1_bobby_contracts.commands import CommandEnvelope
from g1_bobby_unitree_bridge.publisher_ros2 import Ros2RealUnitreeCommandPublisher
from g1_bobby_unitree_bridge.publisher_sdk import SdkRealUnitreeCommandPublisher

command_adapter = TypeAdapter(CommandEnvelope)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute a live Unitree transport publish through a real publisher."
    )
    parser.add_argument(
        "--transport",
        choices=("ros2_real", "sdk_real"),
        required=True,
        help="Real transport to execute.",
    )
    parser.add_argument("--command-json", help="Single command JSON object.")
    parser.add_argument("--script", type=Path, help="JSONL command script to execute.")
    parser.add_argument(
        "--network-interface",
        help="Network interface for DDS/SDK paths when required.",
    )
    parser.add_argument(
        "--sdk-module",
        default="unitree_sdk2py",
        help="SDK module name for sdk_real.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print output JSON.",
    )
    return parser


def load_jsonl_commands(path: Path) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        commands.append(payload)
    return commands


def load_input_commands(args: argparse.Namespace) -> list[CommandEnvelope]:
    if args.command_json:
        payload = json.loads(args.command_json)
        if not isinstance(payload, dict):
            raise ValueError("--command-json must decode to a JSON object")
        return [command_adapter.validate_python(payload)]
    if args.script is not None:
        return [command_adapter.validate_python(item) for item in load_jsonl_commands(args.script)]
    raise ValueError("provide --command-json or --script")


def build_publisher(args: argparse.Namespace):
    if args.transport == "ros2_real":
        return Ros2RealUnitreeCommandPublisher()
    return SdkRealUnitreeCommandPublisher(
        sdk_module=args.sdk_module,
        network_interface=args.network_interface,
    )


async def _run_live_publish(args: argparse.Namespace) -> dict[str, Any]:
    publisher = build_publisher(args)
    commands = load_input_commands(args)
    await publisher.connect()
    try:
        records = []
        execution_plans = []
        execution_results = []
        for command in commands:
            record = await publisher.publish(command)
            records.append(record.model_dump(mode="json"))
            consume_execution_plan = getattr(publisher, "consume_last_execution_plan", None)
            if callable(consume_execution_plan):
                execution_plan = consume_execution_plan()
                if execution_plan is not None:
                    execution_plans.append(execution_plan.model_dump(mode="json"))
            consume_execution_result = getattr(publisher, "consume_last_execution_result", None)
            if callable(consume_execution_result):
                execution_result = consume_execution_result()
                if execution_result is not None:
                    execution_results.append(execution_result.model_dump(mode="json"))
        return {
            "status": "ok",
            "transport": args.transport,
            "records": records,
            "execution_plans": execution_plans,
            "execution_results": execution_results,
        }
    finally:
        await publisher.disconnect()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = asyncio.run(_run_live_publish(args))
    except (ValueError, ValidationError, json.JSONDecodeError, UnitreeTransportConfigurationError) as exc:
        print(f"unitree live publish failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
