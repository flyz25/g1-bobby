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


def build_settings(tmp_path: Path, **kwargs) -> Settings:
    cache_path = kwargs.pop("unitree_state_cache_path", tmp_path / "unitree-state.json")
    return Settings(
        _env_file=None,
        unitree_state_cache_path=cache_path,
        **kwargs,
    )


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
    snapshot = UnitreeDdsSnapshot.model_validate(
        {
            "status": "receiving",
            "timestamp_s": 123.0,
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
    )

    try:
        await runtime.record_unitree_state(snapshot)

        assert await runtime.get_unitree_state() == snapshot
        status = await runtime.unitree_state_status()
        assert status["updates"] == 1
        assert status["status"] == "receiving"
        assert status["age_s"] is not None
    finally:
        await runtime.adapter.disconnect()


@pytest.mark.asyncio
async def test_runtime_projects_unitree_snapshot_into_display_state(tmp_path: Path) -> None:
    runtime = await Runtime.create(build_settings(tmp_path))
    snapshot = UnitreeDdsSnapshot.model_validate(
        {
            "status": "receiving",
            "timestamp_s": 456.0,
            "dds": {
                "domain_id": 1,
                "interface": "lo",
                "robot": "g1",
                "topics": {
                    "low_state": "rt/lowstate",
                    "sport_mode_state": "rt/sportmodestate",
                },
            },
            "sample_counts": {"low_state": 10, "sport_mode_state": 10},
            "ages_s": {"low_state": 0.0, "sport_mode_state": 0.0},
            "low_state": {"motor_count": 35},
            "sport_mode_state": {"position": [0.12, -0.34, 1.28]},
        }
    )

    try:
        await runtime.record_unitree_state(snapshot)

        state = await runtime.get_display_state()
        assert state.connected is True
        assert state.last_state_at == 456.0
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
            "status": "receiving",
            "timestamp_s": 789.0,
            "dds": {
                "domain_id": 1,
                "interface": "lo",
                "robot": "g1",
                "topics": {
                    "low_state": "rt/lowstate",
                    "sport_mode_state": "rt/sportmodestate",
                },
            },
            "sample_counts": {"low_state": 2, "sport_mode_state": 3},
            "ages_s": {"low_state": 0.0, "sport_mode_state": 0.0},
            "low_state": {"motor_count": 35},
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
        assert await reloaded.get_unitree_state() == snapshot
        assert (await reloaded.get_display_state()).pose_label == "unitree-g1 x=0.01 y=0.02 z=1.23"
        status = await reloaded.unitree_state_status()
        assert status["status"] == "receiving"
        assert status["updates"] == 1
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
