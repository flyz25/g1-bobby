from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Sequence

from .dds_introspection import build_dds_introspection_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect known Unitree DDS and ROS2 command/state surfaces.")
    parser.add_argument("--network-interface", help="DDS network interface override.")
    parser.add_argument("--sdk-module", help="SDK module name override.")
    parser.add_argument(
        "--transport",
        choices=("disabled", "dry_run", "ros2_stub", "ros2_plan_stub", "ros2_real", "sdk_plan_stub", "sdk_real"),
        default="sdk_real",
        help="Transport capability to include in the report.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = asyncio.run(
        build_dds_introspection_report(
            network_interface=args.network_interface,
            sdk_module=args.sdk_module,
            transport=args.transport,
        )
    )
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
