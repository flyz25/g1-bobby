from time import time

from g1_bobby_api.command_gate import CommandGate, CommandGateLimits
from g1_bobby_contracts import ErrorCode
from g1_bobby_contracts.commands import CommandType, HeartbeatCommand, HeartbeatPayload


def heartbeat(seq: int, timestamp: float) -> HeartbeatCommand:
    return HeartbeatCommand(
        type=CommandType.HEARTBEAT,
        seq=seq,
        timestamp=timestamp,
        payload=HeartbeatPayload(client_id="quest-dev"),
    )


def test_command_gate_accepts_increasing_fresh_commands() -> None:
    now = time()
    gate = CommandGate()

    first = gate.validate_and_record(heartbeat(1, now), now=now)
    second = gate.validate_and_record(heartbeat(2, now), now=now)

    assert first.accepted
    assert second.accepted


def test_command_gate_rejects_replayed_sequence() -> None:
    now = time()
    gate = CommandGate()

    assert gate.validate_and_record(heartbeat(10, now), now=now).accepted
    decision = gate.validate_and_record(heartbeat(10, now), now=now)

    assert not decision.accepted
    assert decision.code == ErrorCode.REPLAYED_COMMAND
    assert decision.reason == "command sequence must increase"


def test_command_gate_rejects_stale_timestamp() -> None:
    now = time()
    gate = CommandGate(CommandGateLimits(max_age_s=0.5))

    decision = gate.validate_and_record(heartbeat(1, now - 1.0), now=now)

    assert not decision.accepted
    assert decision.code == ErrorCode.STALE_COMMAND
    assert decision.reason == "command timestamp is too old"


def test_command_gate_rejects_future_timestamp() -> None:
    now = time()
    gate = CommandGate(CommandGateLimits(future_tolerance_s=0.1))

    decision = gate.validate_and_record(heartbeat(1, now + 0.5), now=now)

    assert not decision.accepted
    assert decision.code == ErrorCode.STALE_COMMAND
    assert decision.reason == "command timestamp is too far in the future"


def test_command_gate_rejects_rate_limit() -> None:
    now = time()
    gate = CommandGate(CommandGateLimits(max_commands_per_second=2))

    assert gate.validate_and_record(heartbeat(1, now), now=now).accepted
    assert gate.validate_and_record(heartbeat(2, now + 0.01), now=now + 0.01).accepted
    decision = gate.validate_and_record(heartbeat(3, now + 0.02), now=now + 0.02)

    assert not decision.accepted
    assert decision.code == ErrorCode.RATE_LIMITED
    assert decision.reason == "command rate limit exceeded"
