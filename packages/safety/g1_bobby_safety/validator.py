from __future__ import annotations

from dataclasses import dataclass
from time import time

from g1_bobby_contracts.commands import CommandType, MoveVelocityCommand
from g1_bobby_contracts.state import ControlMode, RobotState


@dataclass(frozen=True)
class SafetyLimits:
    max_linear_mps: float = 0.35
    max_angular_radps: float = 0.6
    min_obstacle_distance_m: float = 0.5
    state_ttl_s: float = 1.0
    heartbeat_ttl_s: float = 2.0


@dataclass(frozen=True)
class SafetyDecision:
    accepted: bool
    reason: str

    @classmethod
    def accept(cls) -> "SafetyDecision":
        return cls(accepted=True, reason="accepted")

    @classmethod
    def reject(cls, reason: str) -> "SafetyDecision":
        return cls(accepted=False, reason=reason)


class SafetyValidator:
    def __init__(self, limits: SafetyLimits | None = None) -> None:
        self.limits = limits or SafetyLimits()

    def validate(self, command: object, state: RobotState, now: float | None = None) -> SafetyDecision:
        current_time = now or time()
        command_type = getattr(command, "type", None)

        if command_type in {CommandType.STOP, CommandType.ESTOP, CommandType.HEARTBEAT}:
            return SafetyDecision.accept()

        if command_type == CommandType.SET_MODE:
            if state.estop_engaged:
                return SafetyDecision.reject("cannot change mode while e-stop is engaged")
            if not state.connected:
                return SafetyDecision.reject("robot is not connected")
            return SafetyDecision.accept()

        if command_type != CommandType.MOVE_VELOCITY:
            return SafetyDecision.reject("unsupported command type")

        if not state.connected:
            return SafetyDecision.reject("robot is not connected")
        if state.estop_engaged:
            return SafetyDecision.reject("e-stop is engaged")
        if state.mode != ControlMode.MANUAL:
            return SafetyDecision.reject("robot mode does not allow manual movement")
        if state.last_state_at is None:
            return SafetyDecision.reject("robot state is missing")
        if current_time - state.last_state_at > self.limits.state_ttl_s:
            return SafetyDecision.reject("robot state is stale")
        if state.last_heartbeat_at is None:
            return SafetyDecision.reject("operator heartbeat is missing")
        if current_time - state.last_heartbeat_at > self.limits.heartbeat_ttl_s:
            return SafetyDecision.reject("operator heartbeat is stale")
        if state.obstacle_distance_m is None:
            return SafetyDecision.reject("obstacle distance is missing")
        if state.obstacle_distance_m < self.limits.min_obstacle_distance_m:
            return SafetyDecision.reject("obstacle is too close")

        assert isinstance(command, MoveVelocityCommand)
        if abs(command.payload.linear_x) > self.limits.max_linear_mps:
            return SafetyDecision.reject("linear_x exceeds safety limit")
        if abs(command.payload.linear_y) > self.limits.max_linear_mps:
            return SafetyDecision.reject("linear_y exceeds safety limit")
        if abs(command.payload.angular_z) > self.limits.max_angular_radps:
            return SafetyDecision.reject("angular_z exceeds safety limit")

        return SafetyDecision.accept()

