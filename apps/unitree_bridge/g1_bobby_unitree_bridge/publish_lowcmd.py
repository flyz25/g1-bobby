from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Sequence

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError


@dataclass(frozen=True)
class HgLowCmdFramePlan:
    topic: str
    template: str
    mode_pr: int
    mode_machine: int
    motor_count: int
    motor_mode: int
    q: float
    dq: float
    tau: float
    kp: float
    kd: float
    crc: int


LOWCMD_TEMPLATE_SPECS: tuple[dict[str, object], ...] = (
    {
        "name": "neutral_probe",
        "description": "Zeroed HG lowcmd frame for DDS write-acceptance diagnostics only.",
        "defaults": {
            "topic": "rt/lowcmd",
            "mode_pr": 0,
            "mode_machine": 0,
            "motor_mode": 0,
            "motor_count": 35,
            "q": 0.0,
            "dq": 0.0,
            "tau": 0.0,
            "kp": 0.0,
            "kd": 0.0,
        },
    },
    {
        "name": "hold_zero_mode1",
        "description": "Zero-position hold frame with motor mode 1 and no gains. Diagnostic only.",
        "defaults": {
            "topic": "rt/lowcmd",
            "mode_pr": 0,
            "mode_machine": 0,
            "motor_mode": 1,
            "motor_count": 35,
            "q": 0.0,
            "dq": 0.0,
            "tau": 0.0,
            "kp": 0.0,
            "kd": 0.0,
        },
    },
    {
        "name": "hold_zero_damped",
        "description": "Zero-position hold frame with light gains for acceptance experiments only.",
        "defaults": {
            "topic": "rt/lowcmd",
            "mode_pr": 0,
            "mode_machine": 0,
            "motor_mode": 1,
            "motor_count": 35,
            "q": 0.0,
            "dq": 0.0,
            "tau": 0.0,
            "kp": 20.0,
            "kd": 1.0,
        },
    },
)


def list_lowcmd_templates() -> list[dict[str, object]]:
    return [
        {
            "name": str(template["name"]),
            "description": str(template["description"]),
            "defaults": dict(template["defaults"]),
        }
        for template in LOWCMD_TEMPLATE_SPECS
    ]


def resolve_lowcmd_template(name: str) -> dict[str, object]:
    for template in LOWCMD_TEMPLATE_SPECS:
        if template["name"] == name:
            return {
                "name": str(template["name"]),
                "description": str(template["description"]),
                "defaults": dict(template["defaults"]),
            }
    raise UnitreeTransportConfigurationError(f"unknown lowcmd template: {name}")


class HgLowCmdProbePublisher:
    """Emit HG lowcmd DDS frames for simulator/runtime diagnosis.

    This does not try to map high-level operator commands onto joints. It only
    verifies that a caller can construct and publish a structurally valid
    `unitree_hg.msg.dds_.LowCmd_` frame onto `rt/lowcmd`.
    """

    def __init__(
        self,
        *,
        network_interface: str | None,
        sdk_module: str = "unitree_sdk2py",
        channel_module: str = "unitree_sdk2py.core.channel",
        message_module: str = "unitree_sdk2py.idl.unitree_hg.msg.dds_",
        crc_module: str = "unitree_sdk2py.utils.crc",
        topic: str = "rt/lowcmd",
        write_timeout_s: float = 0.1,
    ) -> None:
        self._network_interface = network_interface
        self._sdk_module = sdk_module
        self._channel_module = channel_module
        self._message_module = message_module
        self._crc_module = crc_module
        self._topic = topic
        self._write_timeout_s = write_timeout_s
        self._connected = False
        self._channel_factory_initialize = None
        self._channel_publisher_class = None
        self._lowcmd_class = None
        self._motorcmd_class = None
        self._crc = None
        self._publisher = None

    async def connect(self) -> None:
        if not self._network_interface:
            raise UnitreeTransportConfigurationError(
                "HG lowcmd probe requires a network interface for DDS transport"
            )
        try:
            import_module(self._sdk_module)
        except ModuleNotFoundError as exc:
            if exc.name == self._sdk_module:
                raise UnitreeTransportConfigurationError(
                    f"Unitree SDK Python module '{self._sdk_module}' is not installed"
                ) from exc
            raise
        try:
            channel_module = import_module(self._channel_module)
            self._channel_factory_initialize = getattr(channel_module, "ChannelFactoryInitialize")
            self._channel_publisher_class = getattr(channel_module, "ChannelPublisher")
        except (ModuleNotFoundError, AttributeError) as exc:
            raise UnitreeTransportConfigurationError(
                f"Unitree SDK DDS channel publisher is not available in {self._channel_module}"
            ) from exc
        try:
            message_module = import_module(self._message_module)
            self._lowcmd_class = getattr(message_module, "LowCmd_")
            self._motorcmd_class = getattr(message_module, "MotorCmd_")
        except (ModuleNotFoundError, AttributeError) as exc:
            raise UnitreeTransportConfigurationError(
                f"Unitree HG DDS messages are not available in {self._message_module}"
            ) from exc
        try:
            crc_module = import_module(self._crc_module)
            self._crc = getattr(crc_module, "CRC")()
        except (ModuleNotFoundError, AttributeError) as exc:
            raise UnitreeTransportConfigurationError(
                f"Unitree CRC helper is not available in {self._crc_module}"
            ) from exc

        self._channel_factory_initialize(0, self._network_interface)
        self._publisher = self._channel_publisher_class(self._topic, self._lowcmd_class)
        self._publisher.Init()
        self._connected = True

    async def disconnect(self) -> None:
        if self._publisher is not None and hasattr(self._publisher, "Close"):
            self._publisher.Close()
        self._publisher = None
        self._connected = False

    def build_frame(
        self,
        *,
        template: str = "neutral_probe",
        mode_pr: int | None = None,
        mode_machine: int | None = None,
        motor_mode: int | None = None,
        q: float | None = None,
        dq: float | None = None,
        tau: float | None = None,
        kp: float | None = None,
        kd: float | None = None,
    ) -> tuple[Any, HgLowCmdFramePlan]:
        if self._lowcmd_class is None or self._motorcmd_class is None or self._crc is None:
            raise UnitreeTransportConfigurationError("HG lowcmd probe publisher is not connected")
        template_defaults = resolve_lowcmd_template(template)["defaults"]
        resolved_mode_pr = int(template_defaults["mode_pr"] if mode_pr is None else mode_pr)
        resolved_mode_machine = int(
            template_defaults["mode_machine"] if mode_machine is None else mode_machine
        )
        resolved_motor_mode = int(template_defaults["motor_mode"] if motor_mode is None else motor_mode)
        resolved_q = float(template_defaults["q"] if q is None else q)
        resolved_dq = float(template_defaults["dq"] if dq is None else dq)
        resolved_tau = float(template_defaults["tau"] if tau is None else tau)
        resolved_kp = float(template_defaults["kp"] if kp is None else kp)
        resolved_kd = float(template_defaults["kd"] if kd is None else kd)

        motors = [
            self._motorcmd_class(
                resolved_motor_mode,
                resolved_q,
                resolved_dq,
                resolved_tau,
                resolved_kp,
                resolved_kd,
                0,
            )
            for _ in range(35)
        ]
        frame = self._lowcmd_class(
            resolved_mode_pr,
            resolved_mode_machine,
            motors,
            [0, 0, 0, 0],
            0,
        )
        crc = int(self._crc.Crc(frame))
        frame.crc = crc
        return frame, HgLowCmdFramePlan(
            topic=self._topic,
            template=template,
            mode_pr=resolved_mode_pr,
            mode_machine=resolved_mode_machine,
            motor_count=len(motors),
            motor_mode=resolved_motor_mode,
            q=resolved_q,
            dq=resolved_dq,
            tau=resolved_tau,
            kp=resolved_kp,
            kd=resolved_kd,
            crc=crc,
        )

    async def publish_frame(
        self,
        *,
        template: str = "neutral_probe",
        mode_pr: int | None = None,
        mode_machine: int | None = None,
        motor_mode: int | None = None,
        q: float | None = None,
        dq: float | None = None,
        tau: float | None = None,
        kp: float | None = None,
        kd: float | None = None,
    ) -> dict[str, Any]:
        if not self._connected or self._publisher is None:
            raise UnitreeTransportConfigurationError("HG lowcmd probe publisher is not connected")
        frame, plan = self.build_frame(
            template=template,
            mode_pr=mode_pr,
            mode_machine=mode_machine,
            motor_mode=motor_mode,
            q=q,
            dq=dq,
            tau=tau,
            kp=kp,
            kd=kd,
        )
        write_result = self._publisher.Write(frame, self._write_timeout_s)
        return {
            "topic": plan.topic,
            "template": plan.template,
            "mode_pr": plan.mode_pr,
            "mode_machine": plan.mode_machine,
            "motor_count": plan.motor_count,
            "motor_mode": plan.motor_mode,
            "q": plan.q,
            "dq": plan.dq,
            "tau": plan.tau,
            "kp": plan.kp,
            "kd": plan.kd,
            "crc": plan.crc,
            "write_result": write_result,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish neutral HG lowcmd DDS frames for Unitree simulator/runtime diagnosis."
    )
    parser.add_argument("--network-interface", required=True, help="DDS network interface.")
    parser.add_argument(
        "--template",
        default="neutral_probe",
        choices=tuple(str(item["name"]) for item in LOWCMD_TEMPLATE_SPECS),
        help="Named lowcmd template to emit.",
    )
    parser.add_argument(
        "--sdk-module",
        default="unitree_sdk2py",
        help="SDK module name for DDS transport helpers.",
    )
    parser.add_argument("--topic", default="rt/lowcmd", help="DDS topic to publish.")
    parser.add_argument("--count", type=int, default=1, help="Number of frames to publish.")
    parser.add_argument(
        "--period-s",
        type=float,
        default=0.02,
        help="Delay between frames when --count > 1.",
    )
    parser.add_argument("--mode-pr", type=int, default=0, help="HG lowcmd mode_pr field.")
    parser.add_argument(
        "--mode-machine",
        type=int,
        default=0,
        help="HG lowcmd mode_machine field.",
    )
    parser.add_argument(
        "--motor-mode",
        type=int,
        default=0,
        help="Per-motor mode value for all 35 motors.",
    )
    parser.add_argument("--q", type=float, default=0.0, help="Per-motor target position.")
    parser.add_argument("--dq", type=float, default=0.0, help="Per-motor target velocity.")
    parser.add_argument("--tau", type=float, default=0.0, help="Per-motor feed-forward torque.")
    parser.add_argument("--kp", type=float, default=0.0, help="Per-motor stiffness gain.")
    parser.add_argument("--kd", type=float, default=0.0, help="Per-motor damping gain.")
    parser.add_argument(
        "--write-timeout-s",
        type=float,
        default=0.1,
        help="Timeout passed to ChannelPublisher.Write().",
    )
    parser.add_argument(
        "--require-write",
        action="store_true",
        help="Exit non-zero if ChannelPublisher.Write() returns false.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


async def _run_publish(args: argparse.Namespace) -> dict[str, Any]:
    if args.count < 1:
        raise ValueError("--count must be >= 1")
    if args.period_s < 0.0:
        raise ValueError("--period-s must be >= 0")

    publisher = HgLowCmdProbePublisher(
        network_interface=args.network_interface,
        sdk_module=args.sdk_module,
        topic=args.topic,
        write_timeout_s=args.write_timeout_s,
    )
    await publisher.connect()
    try:
        template_defaults = resolve_lowcmd_template(args.template)["defaults"]
        frames = []
        write_success = True
        for index in range(args.count):
            frame = await publisher.publish_frame(
                template=args.template,
                mode_pr=args.mode_pr if args.mode_pr != 0 else int(template_defaults["mode_pr"]),
                mode_machine=(
                    args.mode_machine
                    if args.mode_machine != 0
                    else int(template_defaults["mode_machine"])
                ),
                motor_mode=args.motor_mode if args.motor_mode != 0 else int(template_defaults["motor_mode"]),
                q=args.q if args.q != 0.0 else float(template_defaults["q"]),
                dq=args.dq if args.dq != 0.0 else float(template_defaults["dq"]),
                tau=args.tau if args.tau != 0.0 else float(template_defaults["tau"]),
                kp=args.kp if args.kp != 0.0 else float(template_defaults["kp"]),
                kd=args.kd if args.kd != 0.0 else float(template_defaults["kd"]),
            )
            frames.append(frame)
            if frame["write_result"] is False:
                write_success = False
            if index + 1 < args.count and args.period_s > 0.0:
                await asyncio.sleep(args.period_s)
        if args.require_write and not write_success:
            raise UnitreeTransportConfigurationError(
                f"HG lowcmd publisher write was rejected on topic {args.topic}"
            )
        return {
            "status": "ok" if write_success else "write_rejected",
            "topic": args.topic,
            "count": args.count,
            "template": args.template,
            "write_success": write_success,
            "frames": frames,
        }
    finally:
        await publisher.disconnect()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = asyncio.run(_run_publish(args))
    except (ValueError, UnitreeTransportConfigurationError) as exc:
        print(f"unitree lowcmd publish failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
