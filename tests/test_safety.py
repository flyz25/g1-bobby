from time import time

from g1_bobby_contracts.commands import CommandType, MoveVelocityCommand, MoveVelocityPayload
from g1_bobby_contracts.state import ControlMode, RobotState
from g1_bobby_safety import SafetyValidator


def move_command(linear_x: float = 0.1) -> MoveVelocityCommand:
    return MoveVelocityCommand(
        type=CommandType.MOVE_VELOCITY,
        seq=1,
        timestamp=time(),
        payload=MoveVelocityPayload(
            linear_x=linear_x,
            linear_y=0.0,
            angular_z=0.0,
            duration_ms=100,
        ),
    )


def ready_state(now: float) -> RobotState:
    return RobotState(
        connected=True,
        estop_engaged=False,
        mode=ControlMode.MANUAL,
        battery_percent=90.0,
        obstacle_distance_m=2.0,
        last_state_at=now,
        last_heartbeat_at=now,
    )


def test_accepts_safe_movement() -> None:
    now = time()
    decision = SafetyValidator().validate(move_command(), ready_state(now), now=now)
    assert decision.accepted


def test_rejects_missing_heartbeat() -> None:
    now = time()
    state = ready_state(now)
    state.last_heartbeat_at = None
    decision = SafetyValidator().validate(move_command(), state, now=now)
    assert not decision.accepted
    assert decision.reason == "operator heartbeat is missing"


def test_rejects_stale_state() -> None:
    now = time()
    state = ready_state(now)
    state.last_state_at = now - 5
    decision = SafetyValidator().validate(move_command(), state, now=now)
    assert not decision.accepted
    assert decision.reason == "robot state is stale"


def test_rejects_estop() -> None:
    now = time()
    state = ready_state(now)
    state.estop_engaged = True
    decision = SafetyValidator().validate(move_command(), state, now=now)
    assert not decision.accepted
    assert decision.reason == "e-stop is engaged"


def test_rejects_unsafe_velocity() -> None:
    now = time()
    decision = SafetyValidator().validate(move_command(linear_x=0.9), ready_state(now), now=now)
    assert not decision.accepted
    assert decision.reason == "linear_x exceeds safety limit"

