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
- Unitree SDK2 Python from `unitreerobotics/unitree_sdk2_python`
- `g1-bobby-unitree-probe`

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
