from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .diagnostic_report import build_unitree_diagnostic_report


def _fetch_json(url: str) -> dict[str, Any] | None:
    try:
        with urlopen(url, timeout=2.0) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError):
        return None


def _classify(report: dict[str, Any], api_state: dict[str, Any] | None) -> str:
    lowcmd = report.get("lowcmd_write_probe") or {}
    if lowcmd.get("status") == "accepted":
        return "lowcmd_write_accepted"
    if api_state and api_state.get("status") == "receiving" and lowcmd.get("status") == "rejected":
        return "state_only_runtime"
    if report.get("status") == "not_ready":
        return "environment_not_ready"
    return "command_surface_blocked"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Trace the current Unitree simulator/runtime command surface."
    )
    parser.add_argument("--network-interface", required=True, help="DDS network interface.")
    parser.add_argument("--sdk-module", default="unitree_sdk2py", help="SDK module name override.")
    parser.add_argument(
        "--transport",
        default="sdk_real",
        choices=("sdk_real", "ros2_real", "sdk_plan_stub", "ros2_plan_stub"),
        help="Transport capability to include in the trace report.",
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8010",
        help="Optional API base URL for live runtime snapshots.",
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Skip API runtime/state fetches.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


async def _run_trace(args: argparse.Namespace) -> dict[str, Any]:
    diagnostic = await build_unitree_diagnostic_report(
        transport=args.transport,
        network_interface=args.network_interface,
        sdk_module=args.sdk_module,
        probe_lowcmd_write=True,
    )
    api_runtime = None if args.skip_api else _fetch_json(f"{args.api_url.rstrip('/')}/runtime")
    api_unitree_state = None if args.skip_api else _fetch_json(f"{args.api_url.rstrip('/')}/unitree/state")
    return {
        "status": diagnostic["status"],
        "classification": _classify(diagnostic, api_unitree_state),
        "diagnostic_report": diagnostic,
        "api_runtime": api_runtime,
        "api_unitree_state": api_unitree_state,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = asyncio.run(_run_trace(args))
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
