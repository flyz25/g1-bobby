from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from os import environ
import signal
import sys
import threading
import time
from typing import Any, Mapping, Sequence


TOPIC_LOW_STATE = "rt/lowstate"
TOPIC_SPORT_MODE_STATE = "rt/sportmodestate"
DEFAULT_DOMAIN_ID = 1
DEFAULT_INTERFACE = "lo"
DEFAULT_ROBOT = "g1"
DEFAULT_SAMPLE_INTERVAL_S = 1.0
DEFAULT_MAX_MOTORS = 6
HG_LOW_STATE_ROBOTS = {"g1", "h1_2"}


@dataclass(frozen=True)
class UnitreeListenConfig:
    domain_id: int
    interface: str
    robot: str
    duration_s: float | None
    sample_interval_s: float
    max_motors: int
    require_samples: bool


@dataclass
class UnitreeStateCollector:
    domain_id: int
    interface: str
    robot: str
    max_motors: int = DEFAULT_MAX_MOTORS
    low_state: Any | None = None
    sport_state: Any | None = None
    low_state_received_at_s: float | None = None
    sport_state_received_at_s: float | None = None
    low_state_count: int = 0
    sport_state_count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def handle_low_state(self, msg: Any) -> None:
        with self._lock:
            self.low_state = msg
            self.low_state_received_at_s = time.monotonic()
            self.low_state_count += 1

    def handle_sport_state(self, msg: Any) -> None:
        with self._lock:
            self.sport_state = msg
            self.sport_state_received_at_s = time.monotonic()
            self.sport_state_count += 1

    def has_samples(self) -> bool:
        with self._lock:
            return self.low_state_count > 0 or self.sport_state_count > 0

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            now = time.monotonic()
            low_state = self.low_state
            sport_state = self.sport_state
            low_received_at = self.low_state_received_at_s
            sport_received_at = self.sport_state_received_at_s
            low_count = self.low_state_count
            sport_count = self.sport_state_count

        return {
            "status": "receiving" if low_count or sport_count else "waiting_for_samples",
            "timestamp_s": time.time(),
            "dds": {
                "domain_id": self.domain_id,
                "interface": self.interface,
                "robot": self.robot,
                "topics": {
                    "low_state": TOPIC_LOW_STATE,
                    "sport_mode_state": TOPIC_SPORT_MODE_STATE,
                },
            },
            "sample_counts": {
                "low_state": low_count,
                "sport_mode_state": sport_count,
            },
            "ages_s": {
                "low_state": round(now - low_received_at, 3) if low_received_at else None,
                "sport_mode_state": round(now - sport_received_at, 3) if sport_received_at else None,
            },
            "low_state": summarize_low_state(low_state, self.max_motors) if low_state else None,
            "sport_mode_state": summarize_sport_mode_state(sport_state) if sport_state else None,
        }


def env_default(env: Mapping[str, str], key: str, default: str) -> str:
    value = env.get(key)
    if value is None or value == "":
        return default
    return value


def env_float_or_none(env: Mapping[str, str], key: str, default: float | None) -> float | None:
    value = env.get(key)
    if value is None or value == "":
        return default
    parsed = float(value)
    return parsed if parsed > 0 else None


def env_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    value = env.get(key)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def sequence_to_floats(value: Any, limit: int | None = None) -> list[float]:
    if value is None:
        return []
    values = list(value)
    if limit is not None:
        values = values[:limit]
    return [float(item) for item in values]


def optional_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize_imu_state(imu_state: Any) -> dict[str, object]:
    return {
        "quaternion": sequence_to_floats(getattr(imu_state, "quaternion", []), 4),
        "rpy": sequence_to_floats(getattr(imu_state, "rpy", []), 3),
        "gyroscope": sequence_to_floats(getattr(imu_state, "gyroscope", []), 3),
        "accelerometer": sequence_to_floats(getattr(imu_state, "accelerometer", []), 3),
        "temperature": optional_number(getattr(imu_state, "temperature", None)),
    }


def summarize_motor_state(motor_state: Any) -> dict[str, object]:
    return {
        "mode": optional_number(getattr(motor_state, "mode", None)),
        "q": optional_number(getattr(motor_state, "q", None)),
        "dq": optional_number(getattr(motor_state, "dq", None)),
        "tau_est": optional_number(getattr(motor_state, "tau_est", None)),
        "temperature": optional_number(getattr(motor_state, "temperature", None)),
    }


def summarize_low_state(msg: Any, max_motors: int = DEFAULT_MAX_MOTORS) -> dict[str, object]:
    motor_states = list(getattr(msg, "motor_state", []) or [])
    return {
        "tick": optional_number(getattr(msg, "tick", None)),
        "mode_pr": optional_number(getattr(msg, "mode_pr", None)),
        "mode_machine": optional_number(getattr(msg, "mode_machine", None)),
        "motor_count": len(motor_states),
        "motors": [summarize_motor_state(item) for item in motor_states[:max_motors]],
        "imu": summarize_imu_state(getattr(msg, "imu_state", None)),
    }


def summarize_sport_mode_state(msg: Any) -> dict[str, object]:
    return {
        "mode": optional_number(getattr(msg, "mode", None)),
        "position": sequence_to_floats(getattr(msg, "position", []), 3),
        "velocity": sequence_to_floats(getattr(msg, "velocity", []), 3),
        "yaw_speed": optional_number(getattr(msg, "yaw_speed", None)),
        "body_height": optional_number(getattr(msg, "body_height", None)),
    }


def build_parser(env: Mapping[str, str] | None = None) -> argparse.ArgumentParser:
    source_env = environ if env is None else env
    parser = argparse.ArgumentParser(
        description="Listen to Unitree simulator/robot DDS state topics without sending commands."
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
        help="DDS domain id used by the simulator or robot.",
    )
    parser.add_argument(
        "--interface",
        default=env_default(source_env, "G1_BOBBY_UNITREE_DDS_INTERFACE", DEFAULT_INTERFACE),
        help="DDS network interface. Use lo for local simulator mode.",
    )
    parser.add_argument(
        "--robot",
        default=env_default(source_env, "G1_BOBBY_UNITREE_SIM_ROBOT", DEFAULT_ROBOT),
        help="Robot model. G1 uses Unitree HG low-state messages.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=env_float_or_none(source_env, "G1_BOBBY_UNITREE_LISTEN_DURATION_S", None),
        help="Seconds to listen before exiting. Omit or use 0 for forever.",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=float(
            env_default(
                source_env,
                "G1_BOBBY_UNITREE_LISTEN_SAMPLE_INTERVAL_S",
                str(DEFAULT_SAMPLE_INTERVAL_S),
            )
        ),
        help="Seconds between JSON snapshots.",
    )
    parser.add_argument(
        "--max-motors",
        type=int,
        default=int(
            env_default(
                source_env,
                "G1_BOBBY_UNITREE_LISTEN_MAX_MOTORS",
                str(DEFAULT_MAX_MOTORS),
            )
        ),
        help="Maximum number of motor states to include per snapshot.",
    )
    parser.add_argument(
        "--require-samples",
        action=argparse.BooleanOptionalAction,
        default=env_bool(source_env, "G1_BOBBY_UNITREE_LISTEN_REQUIRE_SAMPLES", False),
        help="Exit non-zero if no DDS samples are received before the listener stops.",
    )
    return parser


def config_from_args(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> UnitreeListenConfig:
    args = build_parser(env).parse_args(argv)
    duration_s = args.duration if args.duration and args.duration > 0 else None
    return UnitreeListenConfig(
        domain_id=args.domain_id,
        interface=args.interface,
        robot=args.robot,
        duration_s=duration_s,
        sample_interval_s=max(args.sample_interval, 0.1),
        max_motors=max(args.max_motors, 0),
        require_samples=args.require_samples,
    )


def low_state_type_for_robot(robot: str) -> Any:
    if robot.lower() in HG_LOW_STATE_ROBOTS:
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_

        return LowState_

    from unitree_sdk2py.idl.unitree_go.msg.dds_ import LowState_

    return LowState_


def sport_mode_state_type() -> Any:
    from unitree_sdk2py.idl.unitree_go.msg.dds_ import SportModeState_

    return SportModeState_


def run_listener(config: UnitreeListenConfig) -> int:
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber

    ChannelFactoryInitialize(config.domain_id, config.interface)
    collector = UnitreeStateCollector(
        domain_id=config.domain_id,
        interface=config.interface,
        robot=config.robot,
        max_motors=config.max_motors,
    )

    low_state_subscriber = ChannelSubscriber(TOPIC_LOW_STATE, low_state_type_for_robot(config.robot))
    sport_state_subscriber = ChannelSubscriber(TOPIC_SPORT_MODE_STATE, sport_mode_state_type())
    low_state_subscriber.Init(collector.handle_low_state, 10)
    sport_state_subscriber.Init(collector.handle_sport_state, 10)

    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    previous_sigint = signal.signal(signal.SIGINT, request_stop)
    previous_sigterm = signal.signal(signal.SIGTERM, request_stop)

    try:
        started_at = time.monotonic()
        next_print_at = started_at
        while not stop_requested:
            now = time.monotonic()
            if config.duration_s is not None and now - started_at >= config.duration_s:
                break
            if now >= next_print_at:
                print(json.dumps(collector.snapshot(), sort_keys=True), flush=True)
                next_print_at = now + config.sample_interval_s
            time.sleep(0.05)
    finally:
        low_state_subscriber.Close()
        sport_state_subscriber.Close()
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)

    if config.require_samples and not collector.has_samples():
        print(
            json.dumps(
                {
                    "status": "not_ready",
                    "error": "No Unitree DDS state samples were received.",
                    "dds": {
                        "domain_id": config.domain_id,
                        "interface": config.interface,
                        "robot": config.robot,
                    },
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = config_from_args(argv)
        return run_listener(config)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
