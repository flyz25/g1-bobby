from __future__ import annotations

import argparse
import asyncio
import json
import sys

from g1_bobby_adapters import UnitreeAdapterConfig, describe_unitree_transport_capability

from .publish_lowcmd import HgLowCmdProbePublisher
from .probe import build_probe_status, readiness_errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe the Unitree ROS2 bridge environment.")
    parser.add_argument(
        "--transport",
        choices=(
            "disabled",
            "dry_run",
            "ros2_stub",
            "ros2_plan_stub",
            "ros2_real",
            "sdk_plan_stub",
            "sdk_real",
        ),
        help="Render transport-specific capability for the selected Unitree command transport.",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit non-zero unless ROS2, Unitree SDK, and robot DDS interface are ready.",
    )
    parser.add_argument(
        "--probe-lowcmd-write",
        action="store_true",
        help="Attempt a neutral HG lowcmd write probe against rt/lowcmd.",
    )
    parser.add_argument(
        "--network-interface",
        help="DDS network interface override for readiness and lowcmd write probes.",
    )
    return parser


async def _probe_lowcmd_write(interface: str, sdk_module: str) -> dict[str, object]:
    publisher = HgLowCmdProbePublisher(network_interface=interface, sdk_module=sdk_module)
    await publisher.connect()
    try:
        result = await publisher.publish_neutral_frame()
    finally:
        await publisher.disconnect()
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    status = build_probe_status(network_interface=args.network_interface)
    errors = readiness_errors(status)
    payload = {
        "status": "ready" if not errors else "not_ready",
        "checks": status,
        "errors": errors,
    }
    capability = None
    if args.transport:
        capability = describe_unitree_transport_capability(
            UnitreeAdapterConfig(
                network_interface=str(status["dds_interface"]),
                sdk_module=str(status["unitree_sdk_module"]),
                enable_motor_commands=bool(status["motor_commands_enabled"]),
                command_transport=args.transport,
            )
        )
        payload["transport_capability"] = capability.model_dump(mode="json")
        if capability.ready:
            payload["transport_status"] = "ready"
        elif capability.environment_ready:
            payload["transport_status"] = "blocked"
        else:
            payload["transport_status"] = "not_ready"
    if args.probe_lowcmd_write:
        try:
            payload["lowcmd_write_probe"] = asyncio.run(
                _probe_lowcmd_write(
                    str(status["dds_interface"]),
                    str(status["unitree_sdk_module"]),
                )
            )
        except Exception as exc:
            payload["lowcmd_write_probe"] = {
                "status": "error",
                "detail": str(exc),
                "topic": "rt/lowcmd",
            }
        else:
            payload["lowcmd_write_probe"]["status"] = (
                "accepted"
                if payload["lowcmd_write_probe"].get("write_result") is not False
                else "rejected"
            )
    print(json.dumps(payload, indent=2, sort_keys=True))

    if args.require_ready and (errors or (capability is not None and not capability.ready)):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
