# Unitree Integration Boundary

`UnitreeAdapter` is present as a fail-closed boundary. It lets the API select
`G1_BOBBY_ROBOT_ADAPTER=unitree`, validate required runtime configuration, and
refuse unsafe startup until the real Unitree SDK or ROS2 transport binding is
implemented.

Default local development must remain:

```text
G1_BOBBY_ROBOT_ADAPTER=mock
```

Future hardware mode must provide:

```text
G1_BOBBY_ROBOT_ADAPTER=unitree
G1_BOBBY_UNITREE_NETWORK_INTERFACE=<robot-network-interface>
G1_BOBBY_UNITREE_DDS_INTERFACE=<robot-network-interface>
G1_BOBBY_UNITREE_SDK_MODULE=unitree_sdk2py
G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS=false
```

`G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS` intentionally defaults to `false`.
Changing it to `true` should happen only after the real bridge and manual
hardware checklist exist.

The future adapter must satisfy the same interface as `MockRobotAdapter`:

- `connect()`
- `disconnect()`
- `get_state()`
- `execute(command)`
- `emergency_stop()`
- `reset_emergency_stop()`

No real motor command should bypass:

```text
schema validation -> safety validator -> adapter boundary
```

Before enabling real hardware:

1. Add hardware-specific state freshness checks.
2. Add hardware e-stop verification.
3. Add command rate limiting.
4. Add integration tests against a simulator or dry-run Unitree SDK mode.
5. Add a manual hardware test checklist.

The local planning guide keeps the same architecture rule: Quest/WebSocket
commands enter FastAPI first, then schema validation, safety validation, and
only then a ROS2 or Unitree SDK command boundary. LLM or operator input must not
connect directly to motor control.

## Docker ROS2/Unitree Environment

Use the dedicated container instead of installing ROS2 Humble natively on WSL
Ubuntu 24.04:

```bash
docker compose -f compose.unitree.yml --profile unitree build unitree-ros2
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2
```

The image is based on Ubuntu 22.04 / ROS2 Humble and builds:

- CycloneDDS `releases/0.10.x`
- Unitree ROS2 packages from `unitreerobotics/unitree_ros2`
- Unitree SDK2 C++ from `unitreerobotics/unitree_sdk2`
- Unitree SDK2 Python from `unitreerobotics/unitree_sdk2_python`
- Unitree MuJoCo simulator from `unitreerobotics/unitree_mujoco`
- MuJoCo `3.3.6` from Google DeepMind releases
- `g1-bobby-unitree-probe`
- `g1-bobby-unitree-listen`
- `g1-bobby-unitree-sim`

Local-only probe:

```bash
G1_BOBBY_UNITREE_DDS_INTERFACE=lo \
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2
```

Robot/simulator probe:

```bash
G1_BOBBY_UNITREE_DDS_INTERFACE=<robot-network-interface> \
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-probe --require-ready
```

In WSL2, `eth0` is usually a NAT interface. DDS multicast to a physical robot
may require WSL mirrored networking, a bridged adapter setup, or running this
container on a native Linux host connected to the robot network.

## Unitree MuJoCo Simulator

Use the official Unitree MuJoCo simulator first for local G1 integration:

```bash
docker compose -f compose.unitree.yml --profile sim build unitree-sim
docker compose -f compose.unitree.yml --profile sim run --rm unitree-sim \
  g1-bobby-unitree-sim --dry-run
docker compose -f compose.unitree.yml --profile sim run --rm unitree-sim
```

Read-only DDS state listener, from a second terminal while the simulator is
running:

```bash
docker compose -f compose.unitree.yml --profile sim run --rm unitree-listen \
  g1-bobby-unitree-listen --duration 5 --require-samples
```

Forward received snapshots into the API cache:

```bash
docker compose up --build api
docker compose -f compose.unitree.yml --profile sim run --rm unitree-listen \
  g1-bobby-unitree-listen --api-url http://127.0.0.1:8010
curl http://127.0.0.1:8010/unitree/state
```

For continuous cache repopulation across API restarts, keep the listener
service running instead of a one-shot `run --rm` session:

```bash
docker compose up -d api
docker compose -f compose.unitree.yml --profile sim up -d unitree-listen
```

`unitree-listen` uses `restart: unless-stopped`, so it is suitable as the
long-running DDS-to-API forwarder during simulator sessions.

The same cached snapshot is also attached to HTTP `/state` plus operator
WebSocket `state` and `telemetry` events as `unitree_state`. Those state
surfaces also expose a read-only projected `pose_label` derived from the latest
Unitree sport-mode position when available.

The launcher defaults to:

```text
G1_BOBBY_UNITREE_DDS_INTERFACE=lo
G1_BOBBY_UNITREE_DDS_DOMAIN_ID=1
G1_BOBBY_UNITREE_SIM_ROBOT=g1
G1_BOBBY_UNITREE_SIM_SCENE=scene_29dof.xml
G1_BOBBY_UNITREE_SIM_ELASTIC_BAND=true
G1_BOBBY_UNITREE_SIM_PRINT_SCENE_INFO=false
G1_BOBBY_UNITREE_LISTEN_SAMPLE_INTERVAL_S=1
G1_BOBBY_UNITREE_LISTEN_MAX_MOTORS=6
G1_BOBBY_API_URL=http://127.0.0.1:8010
```

Override the scene when needed:

```bash
G1_BOBBY_UNITREE_SIM_SCENE=scene.xml \
docker compose -f compose.unitree.yml --profile sim run --rm unitree-sim
```

WSLg GUI forwarding uses the host `DISPLAY`, `WAYLAND_DISPLAY`, `/tmp/.X11-unix`,
and `/mnt/wslg` mounts configured in `compose.unitree.yml`.

For G1, the launcher writes `simulate/config.yaml` at startup so the humanoid
virtual elastic band is enabled and the large startup scene dump is disabled.
Click the simulator window once to focus it, then use:

- `Space` to pause/run
- mouse drag to move the camera
- scroll to zoom
- `Backspace` to reset
- `9` to toggle the virtual elastic band
- `7` / `8` to lower or lift the humanoid
- `Ctrl+C` in the terminal to stop the simulator

When using `lo`, CycloneDDS may warn that loopback is not multicast-capable and
then disable multicast. That is acceptable for local simulator smoke tests.

The RTX 3070 is useful for the heavier Unitree IsaacLab path, but that is a
separate GPU simulator stack that needs NVIDIA container runtime, Isaac Sim, and
larger assets. Keep MuJoCo as the baseline before adding IsaacLab.
