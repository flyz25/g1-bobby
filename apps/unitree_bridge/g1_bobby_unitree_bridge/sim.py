from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from os import environ
from pathlib import Path
import subprocess
import sys
from typing import Mapping, Sequence


DEFAULT_SIM_ROOT = Path("/opt/unitree/unitree_mujoco/simulate")
DEFAULT_ROBOT = "g1"
DEFAULT_SCENE = "scene_29dof.xml"
DEFAULT_DOMAIN_ID = 1
DEFAULT_INTERFACE = "lo"
HUMANOID_ROBOTS = {"g1", "h1", "h1_2"}


@dataclass(frozen=True)
class UnitreeMujocoConfig:
    sim_root: Path
    binary: Path
    robot: str
    scene: str
    domain_id: int
    interface: str
    print_scene_information: bool
    enable_elastic_band: bool
    extra_args: tuple[str, ...] = ()


def env_default(env: Mapping[str, str], key: str, default: str) -> str:
    value = env.get(key)
    if value is None or value == "":
        return default
    return value


def env_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    value = env.get(key)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def default_binary_for(sim_root: Path) -> Path:
    return sim_root / "build" / "unitree_mujoco"


def build_parser(env: Mapping[str, str] | None = None) -> argparse.ArgumentParser:
    source_env = environ if env is None else env
    default_robot = env_default(source_env, "G1_BOBBY_UNITREE_SIM_ROBOT", DEFAULT_ROBOT)
    default_sim_root = Path(
        env_default(
            source_env,
            "G1_BOBBY_UNITREE_MUJOCO_SIM_ROOT",
            str(DEFAULT_SIM_ROOT),
        )
    )

    parser = argparse.ArgumentParser(
        description="Launch the official Unitree MuJoCo simulator with G1 Bobby defaults."
    )
    parser.add_argument(
        "--sim-root",
        default=str(default_sim_root),
        help="Path to unitree_mujoco/simulate.",
    )
    parser.add_argument(
        "--binary",
        default=env_default(
            source_env,
            "G1_BOBBY_UNITREE_MUJOCO_BINARY",
            str(default_binary_for(default_sim_root)),
        ),
        help="Path to the compiled unitree_mujoco binary.",
    )
    parser.add_argument(
        "--robot",
        default=default_robot,
        help="Unitree robot model to load.",
    )
    parser.add_argument(
        "--scene",
        default=env_default(source_env, "G1_BOBBY_UNITREE_SIM_SCENE", DEFAULT_SCENE),
        help="Scene XML under unitree_robots/<robot>/, or an absolute XML path.",
    )
    parser.add_argument(
        "--domain-id",
        type=int,
        default=int(
            env_default(
                source_env,
                "G1_BOBBY_UNITREE_DDS_DOMAIN_ID",
                str(DEFAULT_DOMAIN_ID),
            )
        ),
        help="DDS domain id for the simulator.",
    )
    parser.add_argument(
        "--interface",
        default=env_default(source_env, "G1_BOBBY_UNITREE_DDS_INTERFACE", DEFAULT_INTERFACE),
        help="DDS network interface. Use lo for local simulation.",
    )
    parser.add_argument(
        "--print-scene-info",
        action=argparse.BooleanOptionalAction,
        default=env_bool(source_env, "G1_BOBBY_UNITREE_SIM_PRINT_SCENE_INFO", False),
        help="Print all MuJoCo links, joints, actuators, and sensors at startup.",
    )
    parser.add_argument(
        "--elastic-band",
        action=argparse.BooleanOptionalAction,
        default=env_bool(
            source_env,
            "G1_BOBBY_UNITREE_SIM_ELASTIC_BAND",
            default_robot in HUMANOID_ROBOTS,
        ),
        help="Enable the virtual elastic band used by humanoid models.",
    )
    parser.add_argument(
        "--mujoco-help",
        action="store_true",
        help="Forward --help to the Unitree MuJoCo binary.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command and runtime environment without launching the GUI.",
    )
    return parser


def config_from_args(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[UnitreeMujocoConfig, bool]:
    parser = build_parser(env)
    args, extra_args = parser.parse_known_args(argv)
    sim_root = Path(args.sim_root)
    forwarded_args = ["--help"] if args.mujoco_help else extra_args
    config = UnitreeMujocoConfig(
        sim_root=sim_root,
        binary=Path(args.binary),
        robot=args.robot,
        scene=args.scene,
        domain_id=args.domain_id,
        interface=args.interface,
        print_scene_information=args.print_scene_info,
        enable_elastic_band=args.elastic_band,
        extra_args=tuple(forwarded_args),
    )
    return config, args.dry_run


def build_unitree_mujoco_command(config: UnitreeMujocoConfig) -> list[str]:
    return [
        str(config.binary),
        "-r",
        config.robot,
        "-s",
        config.scene,
        "-i",
        str(config.domain_id),
        "-n",
        config.interface,
        *config.extra_args,
    ]


def render_simulator_config(config: UnitreeMujocoConfig) -> str:
    return "\n".join(
        [
            f'robot: "{config.robot}"',
            f'robot_scene: "{config.scene}"',
            f"domain_id: {config.domain_id}",
            f'interface: "{config.interface}"',
            "use_joystick: 0",
            'joystick_type: "xbox"',
            'joystick_device: "/dev/input/js0"',
            "joystick_bits: 16",
            f"print_scene_information: {int(config.print_scene_information)}",
            f"enable_elastic_band: {int(config.enable_elastic_band)}",
            "",
        ]
    )


def write_simulator_config(config: UnitreeMujocoConfig) -> Path:
    config_path = config.sim_root / "config.yaml"
    config_path.write_text(render_simulator_config(config), encoding="utf-8")
    return config_path


def build_runtime_env(
    config: UnitreeMujocoConfig,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    runtime_env = dict(environ if env is None else env)
    library_paths = [
        str(config.sim_root / "mujoco" / "lib"),
        "/opt/unitree_robotics/lib",
    ]
    existing = runtime_env.get("LD_LIBRARY_PATH")
    if existing:
        library_paths.extend(existing.split(":"))

    deduped_paths = list(dict.fromkeys(path for path in library_paths if path))
    runtime_env["LD_LIBRARY_PATH"] = ":".join(deduped_paths)
    return runtime_env


def dry_run_payload(
    config: UnitreeMujocoConfig,
    runtime_env: Mapping[str, str],
) -> dict[str, object]:
    return {
        "command": build_unitree_mujoco_command(config),
        "cwd": str(config.sim_root),
        "simulator_config": render_simulator_config(config),
        "environment": {
            "LD_LIBRARY_PATH": runtime_env.get("LD_LIBRARY_PATH"),
            "G1_BOBBY_UNITREE_DDS_INTERFACE": config.interface,
            "G1_BOBBY_UNITREE_DDS_DOMAIN_ID": config.domain_id,
            "G1_BOBBY_UNITREE_SIM_ELASTIC_BAND": config.enable_elastic_band,
            "G1_BOBBY_UNITREE_SIM_PRINT_SCENE_INFO": config.print_scene_information,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    config, dry_run = config_from_args(argv)
    runtime_env = build_runtime_env(config)

    if dry_run:
        print(json.dumps(dry_run_payload(config, runtime_env), indent=2, sort_keys=True))
        return 0

    if not config.binary.exists():
        print(f"Unitree MuJoCo binary not found: {config.binary}", file=sys.stderr)
        return 2

    write_simulator_config(config)

    return subprocess.call(
        build_unitree_mujoco_command(config),
        cwd=str(config.sim_root),
        env=runtime_env,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
