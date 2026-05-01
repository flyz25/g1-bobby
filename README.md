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
