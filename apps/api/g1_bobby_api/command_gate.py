from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import time

from g1_bobby_contracts import CommandEnvelope, ErrorCode


@dataclass(frozen=True)
class CommandGateLimits:
    max_age_s: float = 1.0
    future_tolerance_s: float = 0.25
    max_commands_per_second: int = 20


@dataclass(frozen=True)
class CommandGateDecision:
    accepted: bool
    code: ErrorCode | None
    reason: str

    @classmethod
    def accept(cls) -> "CommandGateDecision":
        return cls(accepted=True, code=None, reason="accepted")

    @classmethod
    def reject(cls, code: ErrorCode, reason: str) -> "CommandGateDecision":
        return cls(accepted=False, code=code, reason=reason)


class CommandGate:
    def __init__(self, limits: CommandGateLimits | None = None) -> None:
        self.limits = limits or CommandGateLimits()
        self.last_seq: int | None = None
        self._recent_command_times: deque[float] = deque()

    def validate_and_record(
        self,
        command: CommandEnvelope,
        now: float | None = None,
    ) -> CommandGateDecision:
        current_time = time() if now is None else now

        if self.last_seq is not None and command.seq <= self.last_seq:
            return CommandGateDecision.reject(
                ErrorCode.REPLAYED_COMMAND,
                "command sequence must increase",
            )

        if current_time - command.timestamp > self.limits.max_age_s:
            return CommandGateDecision.reject(
                ErrorCode.STALE_COMMAND,
                "command timestamp is too old",
            )

        if command.timestamp - current_time > self.limits.future_tolerance_s:
            return CommandGateDecision.reject(
                ErrorCode.STALE_COMMAND,
                "command timestamp is too far in the future",
            )

        cutoff = current_time - 1.0
        while self._recent_command_times and self._recent_command_times[0] <= cutoff:
            self._recent_command_times.popleft()

        if len(self._recent_command_times) >= self.limits.max_commands_per_second:
            return CommandGateDecision.reject(
                ErrorCode.RATE_LIMITED,
                "command rate limit exceeded",
            )

        self.last_seq = command.seq
        self._recent_command_times.append(current_time)
        return CommandGateDecision.accept()
