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


def test_adapter_factory_rejects_unknown_adapter() -> None:
    with pytest.raises(ValueError, match="unsupported robot adapter"):
        create_robot_adapter("simulator")


@pytest.mark.asyncio
async def test_runtime_create_uses_mock_by_default() -> None:
    runtime = await Runtime.create(Settings(_env_file=None))

    try:
        assert runtime.adapter_name == "mock"
        assert isinstance(runtime.adapter, MockRobotAdapter)
        assert runtime.safety.limits.max_linear_mps == 0.35
    finally:
        await runtime.adapter.disconnect()


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
