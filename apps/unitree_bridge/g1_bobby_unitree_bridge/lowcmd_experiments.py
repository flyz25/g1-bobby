from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Sequence

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError

from .publish_lowcmd import HgLowCmdProbePublisher, list_lowcmd_templates


DEFAULT_PERIODS_S = (0.02, 0.05)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run safe HG lowcmd acceptance experiments against a Unitree simulator/runtime."
    )
    parser.add_argument("--network-interface", required=True, help="DDS network interface.")
    parser.add_argument("--sdk-module", default="unitree_sdk2py", help="SDK module name override.")
    parser.add_argument("--topic", default="rt/lowcmd", help="DDS topic to publish.")
    parser.add_argument("--count", type=int, default=5, help="Frames per experiment case.")
    parser.add_argument(
        "--period-s",
        type=float,
        action="append",
        help="Frame period to test. Repeat to add more periods.",
    )
    parser.add_argument(
        "--template",
        action="append",
        help="Template to test. Repeat to add more templates. Defaults to all templates.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


async def _run_experiments(args: argparse.Namespace) -> dict[str, object]:
    if args.count < 1:
        raise ValueError("--count must be >= 1")
    periods = tuple(args.period_s or DEFAULT_PERIODS_S)
    if any(period < 0.0 for period in periods):
        raise ValueError("--period-s must be >= 0")

    available_templates = {item["name"]: item for item in list_lowcmd_templates()}
    selected_names = tuple(args.template or available_templates.keys())
    missing = [name for name in selected_names if name not in available_templates]
    if missing:
        raise ValueError(f"unknown lowcmd templates: {', '.join(missing)}")

    publisher = HgLowCmdProbePublisher(
        network_interface=args.network_interface,
        sdk_module=args.sdk_module,
        topic=args.topic,
    )
    await publisher.connect()
    try:
        cases: list[dict[str, object]] = []
        for template_name in selected_names:
            for period in periods:
                frames = []
                accepted = True
                for index in range(args.count):
                    frame = await publisher.publish_frame(template=template_name)
                    frames.append(frame)
                    if frame["write_result"] is False:
                        accepted = False
                    if index + 1 < args.count and period > 0.0:
                        await asyncio.sleep(period)
                cases.append(
                    {
                        "template": template_name,
                        "period_s": period,
                        "count": args.count,
                        "accepted": accepted,
                        "first_frame": frames[0],
                        "last_frame": frames[-1],
                    }
                )
        accepted_cases = sum(1 for case in cases if case["accepted"])
        return {
            "status": "accepted" if accepted_cases == len(cases) else "blocked",
            "network_interface": args.network_interface,
            "topic": args.topic,
            "cases": cases,
            "accepted_cases": accepted_cases,
            "total_cases": len(cases),
        }
    finally:
        await publisher.disconnect()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = asyncio.run(_run_experiments(args))
    except (ValueError, UnitreeTransportConfigurationError) as exc:
        print(f"unitree lowcmd experiments failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
