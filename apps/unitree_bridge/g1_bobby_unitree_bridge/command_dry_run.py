from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from pydantic import TypeAdapter, ValidationError

from g1_bobby_contracts.commands import CommandEnvelope, CommandType


command_adapter = TypeAdapter(CommandEnvelope)


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


def translate_command(command: CommandEnvelope) -> dict[str, object]:
    if command.type == CommandType.HEARTBEAT:
        return {
            "seq": command.seq,
            "type": str(command.type),
            "transport": "dry_run",
            "action": "bridge.keepalive",
            "unitree_target": "session",
            "payload": {
                "client_id": command.payload.client_id,
                "timestamp": command.timestamp,
            },
        }

    if command.type == CommandType.SET_MODE:
        return {
            "seq": command.seq,
            "type": str(command.type),
            "transport": "dry_run",
            "action": "bridge.set_mode",
            "unitree_target": "motion_mode",
            "payload": {
                "mode": command.payload.mode,
            },
        }

    if command.type == CommandType.MOVE_VELOCITY:
        return {
            "seq": command.seq,
            "type": str(command.type),
            "transport": "dry_run",
            "action": "motion.velocity",
            "unitree_target": "base_velocity",
            "payload": {
                "linear_x": command.payload.linear_x,
                "linear_y": command.payload.linear_y,
                "angular_z": command.payload.angular_z,
                "duration_ms": command.payload.duration_ms,
            },
        }

    if command.type == CommandType.STOP:
        return {
            "seq": command.seq,
            "type": str(command.type),
            "transport": "dry_run",
            "action": "motion.stop",
            "unitree_target": "base_velocity",
            "payload": {
                "reason": command.payload.reason,
                "linear_x": 0.0,
                "linear_y": 0.0,
                "angular_z": 0.0,
            },
        }

    if command.type == CommandType.ESTOP:
        return {
            "seq": command.seq,
            "type": str(command.type),
            "transport": "dry_run",
            "action": "safety.estop",
            "unitree_target": "motion_gate",
            "payload": {
                "reason": command.payload.reason,
            },
        }

    raise ValueError(f"unsupported command type: {command.type}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Translate operator commands into a Unitree dry-run bridge plan."
    )
    parser.add_argument("--command-json", help="Single command JSON object.")
    parser.add_argument("--script", type=Path, help="JSONL command script to translate.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the output JSON.",
    )
    return parser


def load_input_commands(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.command_json:
        payload = json.loads(args.command_json)
        if not isinstance(payload, dict):
            raise ValueError("--command-json must decode to a JSON object")
        return [payload]
    if args.script is not None:
        return load_jsonl_commands(args.script)
    raise ValueError("provide --command-json or --script")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        commands = [command_adapter.validate_python(item) for item in load_input_commands(args)]
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        print(f"unitree dry-run failed: {exc}", file=sys.stderr)
        return 2

    payload = {
        "status": "ok",
        "transport": "dry_run",
        "command_count": len(commands),
        "commands": [translate_command(command) for command in commands],
    }
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
