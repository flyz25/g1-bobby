import json

import pytest

from g1_bobby_contracts.commands import CommandType, HeartbeatCommand, HeartbeatPayload, MoveVelocityCommand, MoveVelocityPayload
from g1_bobby_unitree_bridge.publisher_plan_stub import PlanStubUnitreeCommandPublisher, main


@pytest.mark.asyncio
async def test_ros2_plan_stub_publisher_emits_ros2_publish_plan() -> None:
    publisher = PlanStubUnitreeCommandPublisher(transport="ros2_plan_stub")
    await publisher.connect()
    try:
        await publisher.publish(
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
        emitted = publisher.emitted_plans()
        assert emitted[0].transport == "ros2_plan_stub"
        assert emitted[0].target == "/api/sport/request"
    finally:
        await publisher.disconnect()


@pytest.mark.asyncio
async def test_sdk_plan_stub_publisher_rejects_unbound_command() -> None:
    publisher = PlanStubUnitreeCommandPublisher(transport="sdk_plan_stub")
    await publisher.connect()
    try:
        with pytest.raises(Exception, match="no confirmed publish-plan binding for command type: heartbeat"):
            await publisher.publish(
                HeartbeatCommand(
                    type=CommandType.HEARTBEAT,
                    seq=5,
                    timestamp=123.0,
                    payload=HeartbeatPayload(client_id="test-client"),
                )
            )
    finally:
        await publisher.disconnect()


def test_plan_stub_cli_prints_emitted_plans(capsys) -> None:
    exit_code = main(
        [
            "--transport",
            "sdk_plan_stub",
            "--command-json",
            '{"type":"set_mode","seq":1,"timestamp":123.0,"payload":{"mode":"manual"}}',
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["emitted_plans"][0]["transport"] == "sdk_plan_stub"
    assert payload["emitted_plans"][0]["payload"]["operation"] == "switch_mode"
    assert payload["execution_results"][0]["status"] == "stub_emitted"
