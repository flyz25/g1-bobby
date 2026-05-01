import json
from pathlib import Path

import pytest

from g1_bobby_adapters import (
    MockRobotAdapter,
    UnitreeAdapter,
    UnitreeAdapterConfig,
    UnitreeAdapterConfigurationError,
    create_robot_adapter,
)
from g1_bobby_api.config import RobotAdapterName, Settings
from g1_bobby_api.runtime import Runtime
from g1_bobby_contracts import UnitreeDdsSnapshot
from g1_bobby_contracts.commands import CommandType, MoveVelocityCommand, MoveVelocityPayload


def build_settings(tmp_path: Path, **kwargs) -> Settings:
    cache_path = kwargs.pop("unitree_state_cache_path", tmp_path / "unitree-state.json")
    command_plan_cache_path = kwargs.pop("unitree_command_plan_cache_path", tmp_path / "unitree-command-plans.jsonl")
    return Settings(
        _env_file=None,
        unitree_state_cache_path=cache_path,
        unitree_command_plan_cache_path=command_plan_cache_path,
        **kwargs,
    )


def unitree_snapshot(timestamp_s: float | None = None) -> dict[str, object]:
    from time import time as now

    return {
        "status": "receiving",
        "timestamp_s": now() if timestamp_s is None else timestamp_s,
        "dds": {
            "domain_id": 1,
            "interface": "lo",
            "robot": "g1",
            "topics": {
                "low_state": "rt/lowstate",
                "sport_mode_state": "rt/sportmodestate",
            },
        },
        "sample_counts": {"low_state": 1, "sport_mode_state": 1},
        "ages_s": {"low_state": 0.0, "sport_mode_state": 0.0},
        "low_state": {"motor_count": 35},
        "sport_mode_state": {"position": [0, 0, 1.2]},
    }


def test_default_settings_select_mock_adapter() -> None:
    settings = Settings(_env_file=None)

    assert settings.robot_adapter == RobotAdapterName.MOCK
    assert isinstance(create_robot_adapter(settings.robot_adapter), MockRobotAdapter)


def test_settings_build_unitree_config() -> None:
    settings = Settings(
        _env_file=None,
        robot_adapter="unitree",
        unitree_network_interface="eth0",
        unitree_sdk_module="unitree_sdk_for_test",
        unitree_enable_motor_commands=True,
    )

    config = settings.unitree_config()

    assert config.network_interface == "eth0"
    assert config.sdk_module == "unitree_sdk_for_test"
    assert config.enable_motor_commands is True


def test_settings_build_safety_limits() -> None:
    settings = Settings(
        _env_file=None,
        safety_max_linear_mps=0.2,
        safety_max_angular_radps=0.4,
        safety_min_obstacle_distance_m=0.8,
        safety_state_ttl_s=0.5,
        safety_heartbeat_ttl_s=1.5,
    )

    limits = settings.safety_limits()

    assert limits.max_linear_mps == 0.2
    assert limits.max_angular_radps == 0.4
    assert limits.min_obstacle_distance_m == 0.8
    assert limits.state_ttl_s == 0.5
    assert limits.heartbeat_ttl_s == 1.5


def test_settings_build_command_gate_limits() -> None:
    settings = Settings(
        _env_file=None,
        command_max_age_s=0.25,
        command_future_tolerance_s=0.1,
        command_max_commands_per_second=4,
    )

    limits = settings.command_gate_limits()

    assert limits.max_age_s == 0.25
    assert limits.future_tolerance_s == 0.1
    assert limits.max_commands_per_second == 4


def test_adapter_factory_rejects_unknown_adapter() -> None:
    with pytest.raises(ValueError, match="unsupported robot adapter"):
        create_robot_adapter("simulator")


@pytest.mark.asyncio
async def test_runtime_create_uses_mock_by_default(tmp_path: Path) -> None:
    runtime = await Runtime.create(build_settings(tmp_path))

    try:
        assert runtime.adapter_name == "mock"
        assert isinstance(runtime.adapter, MockRobotAdapter)
        assert runtime.safety.limits.max_linear_mps == 0.35
        assert runtime.accepted_commands == 0
        assert runtime.rejected_commands == 0
        assert runtime.active_operator_connected is False
    finally:
        await runtime.adapter.disconnect()


@pytest.mark.asyncio
async def test_runtime_allows_only_one_operator_session(tmp_path: Path) -> None:
    runtime = await Runtime.create(build_settings(tmp_path))

    try:
        assert await runtime.claim_operator_session("session-1")
        assert runtime.active_operator_connected is True
        assert not await runtime.claim_operator_session("session-2")

        await runtime.release_operator_session("session-2")
        assert runtime.active_operator_connected is True

        await runtime.release_operator_session("session-1")
        assert runtime.active_operator_connected is False
        assert await runtime.claim_operator_session("session-2")
    finally:
        await runtime.adapter.disconnect()


@pytest.mark.asyncio
async def test_runtime_stores_unitree_state_snapshot(tmp_path: Path) -> None:
    runtime = await Runtime.create(build_settings(tmp_path))
    snapshot = UnitreeDdsSnapshot.model_validate(unitree_snapshot())

    try:
        await runtime.record_unitree_state(snapshot)

        restored = await runtime.get_unitree_state()
        assert restored is not None
        assert restored.status == "receiving"
        assert restored.source == "live"
        assert restored.stale is False
        assert restored.low_state == snapshot.low_state
        status = await runtime.unitree_state_status()
        assert status["updates"] == 1
        assert status["status"] == "receiving"
        assert status["source"] == "live"
        assert status["stale"] is False
        assert status["age_s"] is not None
    finally:
        await runtime.adapter.disconnect()


@pytest.mark.asyncio
async def test_runtime_projects_unitree_snapshot_into_display_state(tmp_path: Path) -> None:
    runtime = await Runtime.create(build_settings(tmp_path))
    snapshot = UnitreeDdsSnapshot.model_validate(
        {
            **unitree_snapshot(),
            "sample_counts": {"low_state": 10, "sport_mode_state": 10},
            "sport_mode_state": {"position": [0.12, -0.34, 1.28]},
        }
    )

    try:
        await runtime.record_unitree_state(snapshot)

        state = await runtime.get_display_state()
        assert state.connected is True
        assert state.last_state_at == snapshot.timestamp_s
        assert state.obstacle_distance_m is None
        assert state.pose_label == "unitree-g1 x=0.12 y=-0.34 z=1.28"
    finally:
        await runtime.adapter.disconnect()


@pytest.mark.asyncio
async def test_runtime_persists_and_reloads_unitree_snapshot(tmp_path: Path) -> None:
    cache_path = tmp_path / "unitree-state.json"
    settings = build_settings(tmp_path, unitree_state_cache_path=cache_path)
    runtime = await Runtime.create(settings)
    snapshot = UnitreeDdsSnapshot.model_validate(
        {
            **unitree_snapshot(),
            "sample_counts": {"low_state": 2, "sport_mode_state": 3},
            "sport_mode_state": {"position": [0.01, 0.02, 1.23]},
        }
    )

    try:
        await runtime.record_unitree_state(snapshot)
        assert cache_path.exists()
    finally:
        await runtime.adapter.disconnect()

    reloaded = await Runtime.create(settings)
    try:
        restored = await reloaded.get_unitree_state()
        assert restored is not None
        assert restored.status == "receiving"
        assert restored.source == "restored"
        assert restored.stale is False
        assert restored.low_state == snapshot.low_state
        assert (await reloaded.get_display_state()).pose_label == "unitree-g1 x=0.01 y=0.02 z=1.23"
        status = await reloaded.unitree_state_status()
        assert status["status"] == "receiving"
        assert status["source"] == "restored"
        assert status["stale"] is False
        assert status["updates"] == 1
    finally:
        await reloaded.adapter.disconnect()


@pytest.mark.asyncio
async def test_runtime_records_unitree_command_plan(tmp_path: Path) -> None:
    runtime = await Runtime.create(build_settings(tmp_path))
    command = MoveVelocityCommand(
        type=CommandType.MOVE_VELOCITY,
        seq=3,
        timestamp=123.0,
        payload=MoveVelocityPayload(
            linear_x=0.1,
            linear_y=0.0,
            angular_z=0.2,
            duration_ms=150,
        ),
    )

    try:
        plan = await runtime.record_unitree_command_plan(command)
        assert plan.plan.action == "motion.velocity"
        assert plan.source == "live"
        assert plan.stale is False

        last_plan = await runtime.get_last_unitree_command_plan()
        assert last_plan is not None
        assert last_plan.plan.seq == 3
        status = await runtime.unitree_command_plan_status()
        assert status["available"] is True
        assert status["plans"] == 1
        assert status["retained"] == 1
        assert status["history_size"] == 10
        assert status["source"] == "live"
        assert status["stale"] is False
    finally:
        await runtime.adapter.disconnect()


@pytest.mark.asyncio
async def test_runtime_broadcasts_unitree_command_plan_to_subscribers(tmp_path: Path) -> None:
    runtime = await Runtime.create(build_settings(tmp_path))
    subscription = await runtime.subscribe_unitree_command_plans()

    try:
        record = await runtime.record_unitree_command_plan(
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
        broadcast = await subscription.get()
        assert broadcast.plan.seq == 3
        assert broadcast.plan.action == "motion.velocity"
        assert broadcast.source == "live"
        assert broadcast.stale is False
        assert broadcast == record
    finally:
        await runtime.unsubscribe_unitree_command_plans(subscription)
        await runtime.adapter.disconnect()


@pytest.mark.asyncio
async def test_runtime_trims_unitree_command_plan_history(tmp_path: Path) -> None:
    runtime = await Runtime.create(build_settings(tmp_path, unitree_command_plan_history_size=2))
    commands = [
        MoveVelocityCommand(
            type=CommandType.MOVE_VELOCITY,
            seq=seq,
            timestamp=100.0 + seq,
            payload=MoveVelocityPayload(
                linear_x=0.1 * seq,
                linear_y=0.0,
                angular_z=0.0,
                duration_ms=100,
            ),
        )
        for seq in (1, 2, 3)
    ]

    try:
        for command in commands:
            await runtime.record_unitree_command_plan(command)

        history = await runtime.get_unitree_command_plan_history()
        assert [record.plan.seq for record in history] == [2, 3]
        status = await runtime.unitree_command_plan_status()
        assert status["plans"] == 3
        assert status["retained"] == 2
        assert status["history_size"] == 2
    finally:
        await runtime.adapter.disconnect()


@pytest.mark.asyncio
async def test_runtime_persists_and_reloads_unitree_command_plan_history(tmp_path: Path) -> None:
    settings = build_settings(
        tmp_path,
        unitree_command_plan_history_size=2,
        unitree_command_plan_cache_path=tmp_path / "unitree-command-plans.jsonl",
    )
    runtime = await Runtime.create(settings)

    try:
        for seq in (1, 2, 3):
            await runtime.record_unitree_command_plan(
                MoveVelocityCommand(
                    type=CommandType.MOVE_VELOCITY,
                    seq=seq,
                    timestamp=100.0 + seq,
                    payload=MoveVelocityPayload(
                        linear_x=0.1 * seq,
                        linear_y=0.0,
                        angular_z=0.0,
                        duration_ms=100,
                    ),
                )
            )
        assert settings.unitree_command_plan_cache_path.exists()
    finally:
        await runtime.adapter.disconnect()

    reloaded = await Runtime.create(settings)
    try:
        history = await reloaded.get_unitree_command_plan_history()
        assert [record.plan.seq for record in history] == [2, 3]
        assert all(record.source == "restored" for record in history)
        last_plan = await reloaded.get_last_unitree_command_plan()
        assert last_plan is not None
        assert last_plan.plan.seq == 3
        assert last_plan.source == "restored"
        assert last_plan.stale is False
        status = await reloaded.unitree_command_plan_status()
        assert status["available"] is True
        assert status["plans"] == 2
        assert status["retained"] == 2
        assert status["history_size"] == 2
        assert status["last_recorded_at"] is not None
        assert status["source"] == "restored"
        assert status["stale"] is False
    finally:
        await reloaded.adapter.disconnect()


@pytest.mark.asyncio
async def test_runtime_restored_unitree_command_plan_can_be_marked_stale(tmp_path: Path) -> None:
    settings = build_settings(
        tmp_path,
        unitree_command_plan_history_size=2,
        unitree_command_plan_ttl_s=0.01,
    )
    runtime = await Runtime.create(settings)

    try:
        await runtime.record_unitree_command_plan(
            MoveVelocityCommand(
                type=CommandType.MOVE_VELOCITY,
                seq=1,
                timestamp=123.0,
                payload=MoveVelocityPayload(
                    linear_x=0.1,
                    linear_y=0.0,
                    angular_z=0.0,
                    duration_ms=100,
                ),
            )
        )
    finally:
        await runtime.adapter.disconnect()

    cache_path = settings.unitree_command_plan_cache_path
    cache_lines = cache_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(cache_lines[-1])
    payload["recorded_at"] = payload["recorded_at"] - 5.0
    cache_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    reloaded = await Runtime.create(settings)
    try:
        last_plan = await reloaded.get_last_unitree_command_plan()
        assert last_plan is not None
        assert last_plan.source == "restored"
        assert last_plan.stale is True
        status = await reloaded.unitree_command_plan_status()
        assert status["source"] == "restored"
        assert status["stale"] is True
    finally:
        await reloaded.adapter.disconnect()


@pytest.mark.asyncio
async def test_unitree_adapter_requires_network_interface() -> None:
    adapter = UnitreeAdapter(UnitreeAdapterConfig(network_interface=None))

    with pytest.raises(UnitreeAdapterConfigurationError, match="UNITREE_NETWORK_INTERFACE"):
        await adapter.connect()


@pytest.mark.asyncio
async def test_unitree_adapter_reports_missing_sdk() -> None:
    adapter = UnitreeAdapter(
        UnitreeAdapterConfig(
            network_interface="eth0",
            sdk_module="missing_unitree_sdk_for_test",
        )
    )

    with pytest.raises(UnitreeAdapterConfigurationError, match="not installed"):
        await adapter.connect()
