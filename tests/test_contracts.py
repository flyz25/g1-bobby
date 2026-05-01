from time import time

import pytest
from pydantic import TypeAdapter, ValidationError

from g1_bobby_contracts.commands import CommandEnvelope, CommandType, MoveVelocityCommand


adapter = TypeAdapter(CommandEnvelope)


def test_validates_move_velocity_command() -> None:
    command = adapter.validate_python(
        {
            "type": "move_velocity",
            "seq": 7,
            "timestamp": time(),
            "payload": {
                "linear_x": 0.1,
                "linear_y": 0.0,
                "angular_z": 0.0,
                "duration_ms": 100,
            },
        }
    )
    assert isinstance(command, MoveVelocityCommand)
    assert command.type == CommandType.MOVE_VELOCITY


def test_rejects_unknown_command_type() -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "type": "dance",
                "seq": 1,
                "timestamp": time(),
                "payload": {},
            }
        )


def test_rejects_extra_payload_fields() -> None:
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "type": "heartbeat",
                "seq": 1,
                "timestamp": time(),
                "payload": {"client_id": "quest", "extra": "nope"},
            }
        )

