from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from pydantic import TypeAdapter, ValidationError

from g1_bobby_contracts.commands import CommandEnvelope
from g1_bobby_unitree_bridge.publisher_ros2 import build_ros2_publish_plan
from g1_bobby_unitree_bridge.publisher_sdk import build_sdk_publish_plan


command_adapter = TypeAdapter(CommandEnvelope)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render Unitree transport publish-plan skeletons without executing transport."
    )
    parser.add_argument(
        "--transport",
        choices=("ros2_real", "sdk_real"),
        required=True,
        help="Transport family to render.",
    )
    parser.add_argument("--command-json", help="Single command JSON object.")
    parser.add_argument("--script", type=Path, help="JSONL command script to render.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the output JSON.",
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


def load_input_commands(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.command_json:
        payload = json.loads(args.command_json)
        if not isinstance(payload, dict):
            raise ValueError("--command-json must decode to a JSON object")
        return [payload]
    if args.script is not None:
        return load_jsonl_commands(args.script)
    raise ValueError("provide --command-json or --script")


def render_plan(transport: str, command: CommandEnvelope) -> dict[str, Any]:
    if transport == "ros2_real":
        plan = build_ros2_publish_plan(command)
    elif transport == "sdk_real":
        plan = build_sdk_publish_plan(command)
    else:
        raise ValueError(f"unsupported transport: {transport}")

    if plan is None:
        raise ValueError(f"no confirmed publish-plan binding for command type: {command.type}")
    return {
        "transport": transport,
        "plan": plan.__dict__,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        commands = [command_adapter.validate_python(item) for item in load_input_commands(args)]
        payload = {
            "status": "ok",
            "transport": args.transport,
            "command_count": len(commands),
            "plans": [render_plan(args.transport, command) for command in commands],
        }
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"unitree publish-plan render failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
