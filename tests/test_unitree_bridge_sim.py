from pathlib import Path

from g1_bobby_unitree_bridge.sim import (
    UnitreeMujocoConfig,
    build_runtime_env,
    build_unitree_mujoco_command,
    config_from_args,
    default_binary_for,
)


def test_default_binary_for_points_to_build_output() -> None:
    assert default_binary_for(Path("/opt/unitree/unitree_mujoco/simulate")) == Path(
        "/opt/unitree/unitree_mujoco/simulate/build/unitree_mujoco"
    )


def test_config_from_args_uses_g1_defaults() -> None:
    config, dry_run = config_from_args(["--dry-run"], env={})

    assert dry_run is True
    assert config.robot == "g1"
    assert config.scene == "scene_29dof.xml"
    assert config.domain_id == 1
    assert config.interface == "lo"


def test_config_from_args_prefers_environment() -> None:
    config, _ = config_from_args(
        [],
        env={
            "G1_BOBBY_UNITREE_MUJOCO_SIM_ROOT": "/sim",
            "G1_BOBBY_UNITREE_MUJOCO_BINARY": "/bin/unitree_mujoco",
            "G1_BOBBY_UNITREE_SIM_ROBOT": "go2",
            "G1_BOBBY_UNITREE_SIM_SCENE": "scene_terrain.xml",
            "G1_BOBBY_UNITREE_DDS_DOMAIN_ID": "7",
            "G1_BOBBY_UNITREE_DDS_INTERFACE": "eth0",
        },
    )

    assert config.sim_root == Path("/sim")
    assert config.binary == Path("/bin/unitree_mujoco")
    assert config.robot == "go2"
    assert config.scene == "scene_terrain.xml"
    assert config.domain_id == 7
    assert config.interface == "eth0"


def test_build_unitree_mujoco_command_maps_to_binary_flags() -> None:
    config = UnitreeMujocoConfig(
        sim_root=Path("/sim"),
        binary=Path("/sim/build/unitree_mujoco"),
        robot="g1",
        scene="scene_29dof.xml",
        domain_id=1,
        interface="lo",
        extra_args=("--help",),
    )

    assert build_unitree_mujoco_command(config) == [
        "/sim/build/unitree_mujoco",
        "-r",
        "g1",
        "-s",
        "scene_29dof.xml",
        "-i",
        "1",
        "-n",
        "lo",
        "--help",
    ]


def test_build_runtime_env_prepends_sim_libraries() -> None:
    config = UnitreeMujocoConfig(
        sim_root=Path("/sim"),
        binary=Path("/sim/build/unitree_mujoco"),
        robot="g1",
        scene="scene.xml",
        domain_id=1,
        interface="lo",
    )

    runtime_env = build_runtime_env(config, {"LD_LIBRARY_PATH": "/existing"})

    assert runtime_env["LD_LIBRARY_PATH"] == "/sim/mujoco/lib:/opt/unitree_robotics/lib:/existing"
