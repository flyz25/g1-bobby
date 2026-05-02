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

Operator dashboard:

```text
http://localhost:8010/dashboard
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

The CLI prints concise event summaries by default. Use `--raw` to keep the
original JSON event stream.

Read-only monitor mode, without sending demo commands:

```bash
g1-bobby-operator --url ws://127.0.0.1:8010/ws/operator --telemetry-only --listen-s 5
```

Persistent monitor mode with automatic reconnect:

```bash
g1-bobby-operator --url ws://127.0.0.1:8010/ws/operator --telemetry-only --watch
```

Accepted `ack` events now also carry `unitree_command_plan`, so the CLI can show
the dry-run Unitree translation inline with each accepted operator command.

Read-only audit stream for command-plan history plus rejected-command audit:

```bash
g1-bobby-operator --url ws://127.0.0.1:8010/ws/operator --audit-stream --watch
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

Dry-run command bridge, without DDS publish:

```bash
g1-bobby-unitree-command-dry-run --command-json \
  '{"type":"move_velocity","seq":3,"timestamp":123.0,"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.0,"duration_ms":100}}'
```

ROS2 bridge-side publish stub, still without DDS publish:

```bash
g1-bobby-unitree-publish-stub --command-json \
  '{"type":"move_velocity","seq":3,"timestamp":123.0,"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.0,"duration_ms":100}}'
```

Inspect concrete ROS2 or SDK publish-plan skeletons, still without transport execution:

```bash
g1-bobby-unitree-publish-plan --transport ros2_real --command-json \
  '{"type":"move_velocity","seq":3,"timestamp":123.0,"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.0,"duration_ms":100}}'
```

Execute through a plan-backed stub that consumes the same publish-plan mapping:

```bash
g1-bobby-unitree-publish-plan-stub --transport sdk_plan_stub --command-json \
  '{"type":"set_mode","seq":1,"timestamp":123.0,"payload":{"mode":"manual"}}'
```

Execute through a real transport when the runtime is available:

```bash
g1-bobby-unitree-publish-live --transport ros2_real --command-json \
  '{"type":"set_mode","seq":1,"timestamp":123.0,"payload":{"mode":"manual"}}'
```

Untuk tunggu response rasmi ROS2 request/response path:

```bash
g1-bobby-unitree-publish-live --transport ros2_real --response-timeout-s 2 \
  --command-json '{"type":"set_mode","seq":1,"timestamp":123.0,"payload":{"mode":"manual"}}'
```

Pada simulator MuJoCo Unitree semasa, DDS state memang hidup tetapi `/api/sport/request`
dan `/api/sport/response` tidak muncul sebagai endpoint ROS2 remote. Jadi mode
`--response-timeout-s` akan fail jelas dan itu menandakan simulator ini bukan
consumer untuk path `ros2_real`.

The API also exposes the latest accepted dry-run translation at:

```text
http://localhost:8010/unitree/command-plan
```

History audit ringkas juga tersedia di:

```text
http://localhost:8010/unitree/command-plans
```

Untuk plan-backed execution stub, API juga expose latest emitted execution plan:

```text
http://localhost:8010/unitree/execution-plan
http://localhost:8010/unitree/execution-plans
```

Dan latest execution outcome untuk stub transport:

```text
http://localhost:8010/unitree/execution-result
http://localhost:8010/unitree/execution-results
```

Dan transport capability semasa untuk adapter Unitree:

```text
http://localhost:8010/unitree/transport-capability
```

Rejected-command audit juga tersedia di:

```text
http://localhost:8010/operator/rejection
http://localhost:8010/operator/rejections
```

Read simulator state from a second terminal:

```bash
docker compose -f compose.unitree.yml --profile sim run --rm unitree-listen \
  g1-bobby-unitree-listen --duration 5 --require-samples
```

Post received simulator state to the API:

```bash
docker compose up --build api
docker compose -f compose.unitree.yml --profile sim run --rm unitree-listen \
  g1-bobby-unitree-listen --api-url http://127.0.0.1:8010
```

For a long-running forwarder that repopulates `/unitree/state` after API
restarts, keep the listener service up instead of `run --rm`:

```bash
docker compose up -d api
docker compose -f compose.unitree.yml --profile sim up -d unitree-listen
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
G1_BOBBY_API_URL=http://127.0.0.1:8010
G1_BOBBY_UNITREE_STATE_CACHE_PATH=.runtime/unitree_state.json
G1_BOBBY_UNITREE_COMMAND_PLAN_CACHE_PATH=.runtime/unitree_command_plans.jsonl
```

The API persists the latest Unitree snapshot to
`G1_BOBBY_UNITREE_STATE_CACHE_PATH`, so a plain API restart can restore
`/unitree/state` and the read-only projected `/state` view even before the next
listener post arrives. It also persists the recent Unitree dry-run command-plan
window to `G1_BOBBY_UNITREE_COMMAND_PLAN_CACHE_PATH`, so
`/unitree/command-plan`, `/unitree/command-plans`, `/operator/rejection`, and
`/operator/rejections` survive a plain API restart as well. Plan-backed
execution stubs also persist `/unitree/execution-plan` and
`/unitree/execution-plans` when their cache path is enabled. Served
`unitree_state` payloads now include:

```text
source=live|restored
stale=true|false
```

Served command-plan records also include:

```text
source=live|restored
stale=true|false
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
G1_BOBBY_UNITREE_NETWORK_INTERFACE=eth0 \
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2
```

Untuk probe transport-specific readiness:

```bash
g1-bobby-unitree-probe --transport ros2_real
g1-bobby-unitree-probe --transport sdk_real --require-ready
```

## WebSocket

Endpoint:

```text
ws://localhost:8010/ws/operator?token=dev-operator-token
```

Read-only audit stream:

```text
ws://localhost:8010/ws/operator/audit?token=dev-operator-token
```

When `/unitree/state` has recent data, the HTTP `/state` response plus operator
`state` and `telemetry` events use a read-only Unitree-backed pose projection
and also carry the latest cached `unitree_state` snapshot.

See [docs/protocol.md](docs/protocol.md) and [samples/operator_messages.jsonl](samples/operator_messages.jsonl).

## MVP Boundary

Default runtime uses `G1_BOBBY_ROBOT_ADAPTER=mock`. `unitree` is available only as a fail-closed boundary for the future Unitree SDK/ROS2 bridge; it requires explicit network interface configuration and still refuses motor commands until the real transport binding is implemented.

Key environment knobs:

```text
G1_BOBBY_ROBOT_ADAPTER=mock
G1_BOBBY_UNITREE_NETWORK_INTERFACE=
G1_BOBBY_UNITREE_COMMAND_TRANSPORT=disabled
G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS=false
G1_BOBBY_SAFETY_MAX_LINEAR_MPS=0.35
G1_BOBBY_SAFETY_MAX_ANGULAR_RADPS=0.6
G1_BOBBY_COMMAND_MAX_COMMANDS_PER_SECOND=20
```

For integration smoke without DDS publish or hardware actuation, the Unitree
adapter now supports:

```text
G1_BOBBY_ROBOT_ADAPTER=unitree
G1_BOBBY_UNITREE_NETWORK_INTERFACE=eth0
G1_BOBBY_UNITREE_SDK_MODULE=unitree_sdk2py
G1_BOBBY_UNITREE_COMMAND_TRANSPORT=dry_run
G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS=true
```

`G1_BOBBY_UNITREE_COMMAND_TRANSPORT=ros2_stub` now routes through the bridge-side
publisher stub instead of the adapter-local dry-run publisher.

`G1_BOBBY_UNITREE_COMMAND_TRANSPORT=ros2_real` now supports live G1 loco
request publishing over ROS2. When `rclpy` and `unitree_api.msg.Request` are
available, `set_mode`, `move_velocity`, and `stop` can publish to
`/api/sport/request`.

That ROS2 transport is now narrowed to the current confirmed G1 intents:

- `set_mode` -> `/api/sport/request` (`unitree_api/msg/Request`)
- `move_velocity` / `stop` -> `/api/sport/request` (`unitree_api/msg/Request`)

At the moment:

- `set_mode` maps to confirmed G1 loco FSM requests
- `move_velocity` / `stop` map to confirmed G1 loco velocity requests
- `heartbeat` / `estop` still have no confirmed ROS2 publish surface in this repo

The repo now also builds a concrete ROS2 publish-plan skeleton for those
bindings, so the remaining gap is runtime publisher wiring rather than command
shape discovery.

For execution rehearsal without ROS2 runtime, `ros2_plan_stub` now consumes that
same publish-plan builder and emits the rendered plan as a stub result.

`G1_BOBBY_UNITREE_COMMAND_TRANSPORT=sdk_real` now exists as a fail-closed
Unitree SDK/DDS skeleton. It verifies `unitree_sdk2py` importability and then
exits with a clear DDS wiring error until native G1 command topic/service
binding is implemented.

That SDK/DDS skeleton is now narrowed to the current confirmed G1 intents:

- `set_mode` -> SportClient/basic service request
- `move_velocity` / `stop` -> `rt/lowcmd` (`unitree_hg.msg.dds_.LowCmd_`)

These bindings are still fail-closed. They track the current best-known
high-level and low-level SDK surfaces from official Unitree SDK material, but no
live DDS command publish occurs yet.

The repo now also builds a concrete SDK publish-plan skeleton for those
bindings, so the remaining gap is native DDS client/publisher execution.

For execution rehearsal without DDS runtime, `sdk_plan_stub` now consumes that
same publish-plan builder and emits the rendered plan as a stub result.

No real motor command should bypass:

```text
schema validation -> safety validator -> adapter boundary
```
