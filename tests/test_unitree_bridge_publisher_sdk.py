from types import SimpleNamespace

import pytest

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError
from g1_bobby_contracts.commands import (
    CommandType,
    HeartbeatCommand,
    HeartbeatPayload,
    MoveVelocityCommand,
    MoveVelocityPayload,
    SetModeCommand,
    SetModePayload,
    StopCommand,
    StopPayload,
)
from g1_bobby_unitree_bridge.publisher_sdk import (
    SdkRealUnitreeCommandPublisher,
    build_sdk_publish_plan,
    resolve_sdk_binding,
)


def test_resolve_sdk_binding_maps_set_mode_to_g1_loco_service() -> None:
    binding = resolve_sdk_binding(
        SetModeCommand(
            type=CommandType.SET_MODE,
            seq=1,
            timestamp=123.0,
            payload=SetModePayload(mode="manual"),
        )
    )

    assert binding is not None
    assert binding.transport_surface == "request_response"
    assert binding.binding_target == "unitree_sdk2py.g1.loco.LocoClient.SetFsmId"
    assert binding.binding_mode == "g1_loco_service"


def test_resolve_sdk_binding_maps_velocity_to_g1_loco_service() -> None:
    binding = resolve_sdk_binding(
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

    assert binding is not None
    assert binding.transport_surface == "request_response"
    assert binding.binding_target == "unitree_sdk2py.g1.loco.LocoClient.SetVelocity"
    assert binding.binding_mode == "g1_loco_service"


def test_resolve_sdk_binding_maps_stop_to_g1_loco_service() -> None:
    binding = resolve_sdk_binding(
        StopCommand(
            type=CommandType.STOP,
            seq=4,
            timestamp=123.0,
            payload=StopPayload(reason="test_stop"),
        )
    )

    assert binding is not None
    assert binding.binding_target == "unitree_sdk2py.g1.loco.LocoClient.SetVelocity"


def test_resolve_sdk_binding_returns_none_for_heartbeat() -> None:
    binding = resolve_sdk_binding(
        HeartbeatCommand(
            type=CommandType.HEARTBEAT,
            seq=5,
            timestamp=123.0,
            payload=HeartbeatPayload(client_id="test-client"),
        )
    )

    assert binding is None


def test_build_sdk_publish_plan_maps_set_mode_payload() -> None:
    plan = build_sdk_publish_plan(
        SetModeCommand(
            type=CommandType.SET_MODE,
            seq=1,
            timestamp=123.0,
            payload=SetModePayload(mode="manual"),
        )
    )

    assert plan is not None
    assert plan.binding_target == "unitree_sdk2py.g1.loco.LocoClient.SetFsmId"
    assert plan.payload == {
        "operation": "SetFsmId",
        "fsm_id": 500,
    }


def test_build_sdk_publish_plan_maps_velocity_payload() -> None:
    plan = build_sdk_publish_plan(
        MoveVelocityCommand(
            type=CommandType.MOVE_VELOCITY,
            seq=3,
            timestamp=123.0,
            payload=MoveVelocityPayload(
                linear_x=0.1,
                linear_y=0.0,
                angular_z=0.2,
                duration_ms=100,
            ),
        )
    )

    assert plan is not None
    assert plan.binding_target == "unitree_sdk2py.g1.loco.LocoClient.SetVelocity"
    assert plan.payload == {
        "operation": "SetVelocity",
        "velocity": {"linear_x": 0.1, "linear_y": 0.0, "angular_z": 0.2},
        "duration_s": 0.1,
    }


def test_build_sdk_publish_plan_returns_none_for_heartbeat() -> None:
    plan = build_sdk_publish_plan(
        HeartbeatCommand(
            type=CommandType.HEARTBEAT,
            seq=5,
            timestamp=123.0,
            payload=HeartbeatPayload(client_id="test-client"),
        )
    )

    assert plan is None


def test_build_sdk_publish_plan_rejects_unconfirmed_assist_mode() -> None:
    with pytest.raises(
        UnitreeTransportConfigurationError,
        match="no confirmed G1 loco FSM mapping for set_mode=assist",
    ):
        build_sdk_publish_plan(
            SetModeCommand(
                type=CommandType.SET_MODE,
                seq=1,
                timestamp=123.0,
                payload=SetModePayload(mode="assist"),
            )
        )


class _FakeLocoClient:
    def __init__(self) -> None:
        self.timeout = None
        self.initialized = False
        self.calls: list[tuple[str, tuple[float | int, ...]]] = []
        self.return_code = 0

    def SetTimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def Init(self) -> None:
        self.initialized = True

    def SetFsmId(self, fsm_id: int) -> int:
        self.calls.append(("SetFsmId", (fsm_id,)))
        return self.return_code

    def SetVelocity(self, vx: float, vy: float, omega: float, duration: float) -> int:
        self.calls.append(("SetVelocity", (vx, vy, omega, duration)))
        return self.return_code


@pytest.mark.asyncio
async def test_sdk_real_publisher_connects_and_publishes_set_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, str]] = []
    fake_client = _FakeLocoClient()
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "fake_channel",
        SimpleNamespace(ChannelFactoryInitialize=lambda domain_id, iface=None: calls.append((domain_id, iface))),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "fake_loco",
        SimpleNamespace(LocoClient=lambda: fake_client),
    )
    publisher = SdkRealUnitreeCommandPublisher(
        sdk_module="unitree_sdk_for_test",
        network_interface="eth0",
        timeout_s=3.5,
        channel_module="fake_channel",
        loco_client_module="fake_loco",
    )

    await publisher.connect()
    try:
        record = await publisher.publish(
            SetModeCommand(
                type=CommandType.SET_MODE,
                seq=1,
                timestamp=123.0,
                payload=SetModePayload(mode="manual"),
            )
        )
        assert record.plan.transport == "sdk_real"
        assert calls == [(0, "eth0")]
        assert fake_client.initialized is True
        assert fake_client.timeout == 3.5
        assert fake_client.calls == [("SetFsmId", (500,))]
        execution_result = publisher.consume_last_execution_result()
        assert execution_result is not None
        assert execution_result.status == "responded"
        response = publisher.consume_last_response()
        assert response == {"status_code": 0, "status_label": "RPC_OK", "operation": "SetFsmId"}
    finally:
        await publisher.disconnect()


@pytest.mark.asyncio
async def test_sdk_real_publisher_publishes_move_velocity(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeLocoClient()
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "fake_channel",
        SimpleNamespace(ChannelFactoryInitialize=lambda domain_id, iface=None: None),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "fake_loco",
        SimpleNamespace(LocoClient=lambda: fake_client),
    )
    publisher = SdkRealUnitreeCommandPublisher(
        sdk_module="unitree_sdk_for_test",
        network_interface="eth0",
        channel_module="fake_channel",
        loco_client_module="fake_loco",
    )

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
        assert fake_client.calls == [("SetVelocity", (0.1, 0.0, 0.0, 0.1))]
    finally:
        await publisher.disconnect()


@pytest.mark.asyncio
async def test_sdk_real_publisher_surfaces_non_zero_status(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeLocoClient()
    fake_client.return_code = 7302
    monkeypatch.setitem(__import__("sys").modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(
        __import__("sys").modules,
        "fake_channel",
        SimpleNamespace(ChannelFactoryInitialize=lambda domain_id, iface=None: None),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "fake_loco",
        SimpleNamespace(LocoClient=lambda: fake_client),
    )
    publisher = SdkRealUnitreeCommandPublisher(
        sdk_module="unitree_sdk_for_test",
        network_interface="eth0",
        channel_module="fake_channel",
        loco_client_module="fake_loco",
    )

    await publisher.connect()
    try:
        with pytest.raises(
            UnitreeTransportConfigurationError,
            match=r"status_code=7302 \(UNKNOWN_STATUS\)",
        ):
            await publisher.publish(
                SetModeCommand(
                    type=CommandType.SET_MODE,
                    seq=1,
                    timestamp=123.0,
                    payload=SetModePayload(mode="manual"),
                )
            )
        execution_result = publisher.consume_last_execution_result()
        assert execution_result is not None
        assert execution_result.detail == "sdk status_code=7302 (UNKNOWN_STATUS)"
    finally:
        await publisher.disconnect()


@pytest.mark.asyncio
async def test_sdk_real_publisher_rejects_unbound_heartbeat() -> None:
    publisher = SdkRealUnitreeCommandPublisher(network_interface="eth0")

    with pytest.raises(
        UnitreeTransportConfigurationError,
        match="no confirmed binding yet for command type: heartbeat",
    ):
        await publisher.publish(
            HeartbeatCommand(
                type=CommandType.HEARTBEAT,
                seq=5,
                timestamp=123.0,
                payload=HeartbeatPayload(client_id="test-client"),
            )
        )
