from pathlib import Path

from g1_bobby_unitree_bridge.sim import (
    UnitreeMujocoConfig,
    build_runtime_env,
    build_unitree_mujoco_command,
    config_from_args,
    default_binary_for,
    render_simulator_config,
    write_simulator_config,
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
    assert config.enable_elastic_band is True
    assert config.print_scene_information is False


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
            "G1_BOBBY_UNITREE_SIM_ELASTIC_BAND": "false",
            "G1_BOBBY_UNITREE_SIM_PRINT_SCENE_INFO": "true",
        },
    )

    assert config.sim_root == Path("/sim")
    assert config.binary == Path("/bin/unitree_mujoco")
    assert config.robot == "go2"
    assert config.scene == "scene_terrain.xml"
    assert config.domain_id == 7
    assert config.interface == "eth0"
    assert config.enable_elastic_band is False
    assert config.print_scene_information is True


def test_build_unitree_mujoco_command_maps_to_binary_flags() -> None:
    config = UnitreeMujocoConfig(
        sim_root=Path("/sim"),
        binary=Path("/sim/build/unitree_mujoco"),
        robot="g1",
        scene="scene_29dof.xml",
        domain_id=1,
        interface="lo",
        print_scene_information=False,
        enable_elastic_band=True,
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
        print_scene_information=False,
        enable_elastic_band=True,
    )

    runtime_env = build_runtime_env(config, {"LD_LIBRARY_PATH": "/existing"})

    assert runtime_env["LD_LIBRARY_PATH"] == "/sim/mujoco/lib:/opt/unitree_robotics/lib:/existing"


def test_render_simulator_config_uses_humanoid_interaction_defaults() -> None:
    config = UnitreeMujocoConfig(
        sim_root=Path("/sim"),
        binary=Path("/sim/build/unitree_mujoco"),
        robot="g1",
        scene="scene_29dof.xml",
        domain_id=1,
        interface="lo",
        print_scene_information=False,
        enable_elastic_band=True,
    )

    assert render_simulator_config(config) == (
        'robot: "g1"\n'
        'robot_scene: "scene_29dof.xml"\n'
        "domain_id: 1\n"
        'interface: "lo"\n'
        "use_joystick: 0\n"
        'joystick_type: "xbox"\n'
        'joystick_device: "/dev/input/js0"\n'
        "joystick_bits: 16\n"
        "print_scene_information: 0\n"
        "enable_elastic_band: 1\n"
    )


def test_write_simulator_config_writes_config_yaml(tmp_path: Path) -> None:
    config = UnitreeMujocoConfig(
        sim_root=tmp_path,
        binary=tmp_path / "build" / "unitree_mujoco",
        robot="go2",
        scene="scene.xml",
        domain_id=3,
        interface="lo",
        print_scene_information=True,
        enable_elastic_band=False,
    )

    config_path = write_simulator_config(config)

    assert config_path == tmp_path / "config.yaml"
    assert 'robot: "go2"' in config_path.read_text(encoding="utf-8")
    assert "print_scene_information: 1" in config_path.read_text(encoding="utf-8")
    assert "enable_elastic_band: 0" in config_path.read_text(encoding="utf-8")
