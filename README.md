# G1 Bobby

Mock-first teleoperation spine for Unitree G1 development.

The MVP does **not** send real robot motor commands. It provides:

- FastAPI HTTP endpoints
- WebSocket JSON operator protocol
- fail-closed safety validation
- stateful mock robot adapter
- placeholder boundary for future Unitree integration

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Open:

```text
http://localhost:8010/health
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

Real Unitree SDK and ROS2 integration are intentionally deferred. The first milestone is to stabilize command contracts, safety behavior, and operator flow using `MockRobotAdapter`.
