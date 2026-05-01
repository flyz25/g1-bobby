import json

import pytest

from g1_bobby_unitree_bridge.publisher_stub import Ros2StubUnitreeCommandPublisher, main
from g1_bobby_contracts.commands import CommandType, MoveVelocityCommand, MoveVelocityPayload


@pytest.mark.asyncio
async def test_ros2_stub_publisher_marks_transport() -> None:
    publisher = Ros2StubUnitreeCommandPublisher()
    await publisher.connect()
    try:
        record = await publisher.publish(
            MoveVelocityCommand(
                type=CommandType.MOVE_VELOCITY,
                seq=3,
                timestamp=123.0,
                payload=MoveVelocityPayload(
                    linear_x=0.1,
                    linear_y=0.0,
                    angular_z=0.0,
                    duration_ms=100,
                ),
            )
        )
        assert record.event_id == 1
        assert record.plan.transport == "ros2_stub"
        assert record.plan.action == "motion.velocity"
    finally:
        await publisher.disconnect()


def test_ros2_stub_cli_prints_records(capsys) -> None:
    exit_code = main(
        [
            "--command-json",
            '{"type":"move_velocity","seq":3,"timestamp":123.0,"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.0,"duration_ms":100}}',
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["records"][0]["plan"]["transport"] == "ros2_stub"
