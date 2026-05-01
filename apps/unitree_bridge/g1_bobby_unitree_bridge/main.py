from __future__ import annotations

import argparse
import json
import sys

from .probe import build_probe_status, readiness_errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe the Unitree ROS2 bridge environment.")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit non-zero unless ROS2, Unitree SDK, and robot DDS interface are ready.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    status = build_probe_status()
    errors = readiness_errors(status)
    payload = {
        "status": "ready" if not errors else "not_ready",
        "checks": status,
        "errors": errors,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if args.require_ready and errors:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
