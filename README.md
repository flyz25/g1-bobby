# G1 Bobby

Mock-first teleoperation spine for Unitree G1 development.

The MVP does **not** send real robot motor commands. It provides:

- FastAPI HTTP endpoints
- WebSocket JSON operator protocol
- fail-closed safety validation
- stateful mock robot adapter
- fail-closed boundary for future Unitree integration

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Open:

```text
http://localhost:8010/health
```

Runtime status:

```text
http://localhost:8010/runtime
```

Resetting e-stop over HTTP requires the operator token:

```bash
curl -X POST http://localhost:8010/reset-estop \
  -H "X-Operator-Token: dev-operator-token"
```

Run tests with Docker:

```bash
docker compose run --rm api pytest
docker compose down
```

Optional local Python workflow, if `python3.12-venv` is installed:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Operator CLI

Start the API, then send a safe mock nudge sequence:

```bash
uvicorn g1_bobby_api.app:app --host 0.0.0.0 --port 8010
g1-bobby-operator
```

Run a JSONL command script with fresh timestamps:

```bash
g1-bobby-operator --script samples/operator_messages.jsonl
```

## Unitree ROS2 Container

The robot stack runs in a separate Ubuntu 22.04 / ROS2 Humble container so WSL
Ubuntu 24.04 stays clean:

```bash
docker compose -f compose.unitree.yml --profile unitree build unitree-ros2
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2
```

## Unitree MuJoCo Simulator

The same Unitree container also builds the official `unitree_mujoco` simulator
with G1 defaults:

```bash
docker compose -f compose.unitree.yml --profile sim build unitree-sim
docker compose -f compose.unitree.yml --profile sim run --rm unitree-sim \
  g1-bobby-unitree-sim --dry-run
docker compose -f compose.unitree.yml --profile sim run --rm unitree-sim
```

Read simulator state from a second terminal:

```bash
docker compose -f compose.unitree.yml --profile sim run --rm unitree-listen \
  g1-bobby-unitree-listen --duration 5 --require-samples
```

Defaults:

```text
G1_BOBBY_UNITREE_DDS_INTERFACE=lo
G1_BOBBY_UNITREE_DDS_DOMAIN_ID=1
G1_BOBBY_UNITREE_SIM_ROBOT=g1
G1_BOBBY_UNITREE_SIM_SCENE=scene_29dof.xml
G1_BOBBY_UNITREE_SIM_ELASTIC_BAND=true
G1_BOBBY_UNITREE_SIM_PRINT_SCENE_INFO=false
G1_BOBBY_UNITREE_LISTEN_SAMPLE_INTERVAL_S=1
G1_BOBBY_UNITREE_LISTEN_MAX_MOTORS=6
```

WSLg should provide `DISPLAY`, `WAYLAND_DISPLAY`, and `/mnt/wslg`. RTX GPU
acceleration is more relevant for the heavier IsaacLab path; MuJoCo is the
baseline simulator for local integration.

For G1, click the simulator window once to focus it. Use `Space` to pause/run,
mouse drag to move the camera, scroll to zoom, `Backspace` to reset, `9` to
toggle the virtual elastic band, and `7` / `8` to lower or lift the humanoid.
Stop the simulator from the terminal with `Ctrl+C`.

The local `lo` interface can print a CycloneDDS multicast warning during smoke
tests; that is expected for this local simulator path.

Default DDS interface is `lo` for local probing. When a real robot or simulator
network is reachable, set the DDS interface explicitly:

```bash
G1_BOBBY_UNITREE_DDS_INTERFACE=eth0 \
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2
```

## WebSocket

Endpoint:

```text
ws://localhost:8010/ws/operator?token=dev-operator-token
```

See [docs/protocol.md](docs/protocol.md) and [samples/operator_messages.jsonl](samples/operator_messages.jsonl).

## MVP Boundary

Default runtime uses `G1_BOBBY_ROBOT_ADAPTER=mock`. `unitree` is available only as a fail-closed boundary for the future Unitree SDK/ROS2 bridge; it requires explicit network interface configuration and still refuses motor commands until the real transport binding is implemented.

Key environment knobs:

```text
G1_BOBBY_ROBOT_ADAPTER=mock
G1_BOBBY_UNITREE_NETWORK_INTERFACE=
G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS=false
G1_BOBBY_SAFETY_MAX_LINEAR_MPS=0.35
G1_BOBBY_SAFETY_MAX_ANGULAR_RADPS=0.6
G1_BOBBY_COMMAND_MAX_COMMANDS_PER_SECOND=20
```

No real motor command should bypass:

```text
schema validation -> safety validator -> adapter boundary
```
