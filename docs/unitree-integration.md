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

Inside that adapter boundary, the current repo now supports two transport modes:

- `disabled`: fail-closed default
- `dry_run`: publishable Unitree translation path without DDS publish or hardware actuation
- `ros2_stub`: bridge-side publish stub without DDS publish or hardware actuation
- `ros2_real`: live G1 loco ROS2 request publisher for confirmed `/api/sport/request` control
- `sdk_real`: live `unitree_sdk2py` G1 loco client publisher for confirmed request/response control

This is still not full robot actuation validation. It is the software transport
seam plus the currently confirmed live request paths.

Current confirmed ROS2 binding intents in the repo are:

- `set_mode` -> `/api/sport/request` with `unitree_api/msg/Request`
- `move_velocity` -> `/api/sport/request` with `unitree_api/msg/Request`
- `stop` -> `/api/sport/request` with `unitree_api/msg/Request`

At the moment, `ros2_real` can publish `set_mode`, `move_velocity`, and `stop`
live through `/api/sport/request` when `rclpy` and `unitree_api.msg.Request`
are available. `heartbeat` / `estop` still do not have a confirmed ROS2
publish surface in this repo.

The current repo also builds a concrete ROS2 publish-plan skeleton for these
commands. Live ROS2 publish now exists for the confirmed G1 loco request path.

Current confirmed Unitree SDK/DDS binding intents in the repo are:

- `set_mode` -> `unitree_sdk2py.g1.loco.LocoClient.SetFsmId`
- `move_velocity` -> `unitree_sdk2py.g1.loco.LocoClient.SetVelocity`
- `stop` -> `unitree_sdk2py.g1.loco.LocoClient.SetVelocity`

These now execute real SDK request/response calls through `unitree_sdk2py`.
`heartbeat` and `estop` do not yet have a confirmed SDK publish surface in this
repo, so `sdk_real` still fails closed for them.

Observed simulator behavior with the current Unitree MuJoCo image:

- DDS state topics such as `rt/lowstate` and `rt/sportmodestate` are active.
- `sdk_real` reaches `unitree_sdk2py.g1.loco.LocoClient`, but calls such as
  `SetFsmId` and `SetVelocity` return `3102 (RPC_ERR_CLIENT_SEND)`.
- That points to the simulator not exposing the matching SDK RPC service path,
  even though DDS state transport is alive.

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
- `g1-bobby-unitree-command-dry-run`
- `g1-bobby-unitree-publish-plan`
- `g1-bobby-unitree-publish-plan-stub`
- `g1-bobby-unitree-sim`

Local-only probe:

```bash
G1_BOBBY_UNITREE_NETWORK_INTERFACE=lo \
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2
```

Robot/simulator probe:

```bash
G1_BOBBY_UNITREE_NETWORK_INTERFACE=<robot-network-interface> \
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-probe --require-ready
```

Transport-specific capability probe:

```bash
G1_BOBBY_UNITREE_NETWORK_INTERFACE=<robot-network-interface> \
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-probe --transport ros2_real

docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-probe --network-interface eth0 --probe-lowcmd-write

docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-diagnostic-report --network-interface eth0 --transport sdk_real --probe-lowcmd-write

docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-lowcmd-experiments --network-interface eth0 --count 5 --period-s 0 \
  --template neutral_probe --template hold_zero_damped

docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-sim-trace --network-interface eth0 --transport sdk_real

docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-dds-introspect --network-interface eth0 --transport sdk_real
```

Dry-run command translation, without DDS publish:

```bash
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-command-dry-run --command-json \
  '{"type":"move_velocity","seq":3,"timestamp":123.0,"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.0,"duration_ms":100}}'
```

This command bridge is intentionally audit-only for now. It translates validated
operator commands into a concrete Unitree dry-run action plan, but it does not
publish DDS or send motor commands yet.

Concrete ROS2 or SDK publish-plan rendering, without transport execution:

```bash
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-publish-plan --transport sdk_real --command-json \
  '{"type":"set_mode","seq":1,"timestamp":123.0,"payload":{"mode":"manual"}}'
```

Plan-backed execution stubs, still without live ROS2 or DDS publish:

```bash
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-publish-plan-stub --transport ros2_plan_stub --command-json \
  '{"type":"move_velocity","seq":3,"timestamp":123.0,"payload":{"linear_x":0.1,"linear_y":0.0,"angular_z":0.0,"duration_ms":100}}'
```

Live transport execution, when the runtime really exposes the target surface:

```bash
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-publish-live --transport ros2_real --command-json \
  '{"type":"set_mode","seq":1,"timestamp":123.0,"payload":{"mode":"manual"}}'
```

To wait for a matching ROS2 response:

```bash
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-publish-live --transport ros2_real --response-timeout-s 2 \
  --command-json '{"type":"set_mode","seq":1,"timestamp":123.0,"payload":{"mode":"manual"}}'
```

Observed simulator behavior with the current Unitree MuJoCo image:

- DDS state topics such as `rt/lowstate` and `rt/sportmodestate` are active.
- The simulator does not expose remote ROS2 endpoints on `/api/sport/request`
  or `/api/sport/response`.
- Because of that, `ros2_real --response-timeout-s ...` fails clearly against
  the simulator, which points to a transport mismatch rather than a malformed
  request payload.

To probe the lower DDS surface directly, there is also a neutral HG lowcmd
publisher:

```bash
docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  python3 -m g1_bobby_unitree_bridge.publish_lowcmd --network-interface lo --count 5
```

That path emits structurally valid `unitree_hg.msg.dds_.LowCmd_` frames to
`rt/lowcmd` with a computed CRC. It is intentionally narrower than the teleop
spine: it proves DDS publishability, not safe high-level motion control.

The API now also exposes:

```text
GET /unitree/diagnostic-report
GET /unitree/lowcmd-templates
GET /unitree/sim-trace
GET /unitree/lowcmd-experiments
GET /unitree/dds-introspection
GET /unitree/source-trace
GET /unitree/export-bundle
```

The operator dashboard consumes the same report so transport blockers, current
readiness, lowcmd probe results, exportable diagnostic/audit bundles, and
history filtering are visible without leaving `/dashboard`.

At runtime, the API stores the latest accepted dry-run plan and exposes it via:

```text
GET /unitree/command-plan
```

It also keeps a short in-memory history window for recent accepted plans:

```text
GET /unitree/command-plans
```

For plan-backed execution stubs, the API also stores the latest emitted
transport-facing execution plan:

```text
GET /unitree/execution-plan
GET /unitree/execution-plans
```

These records differ from `/unitree/command-plan`: they show the normalized
ROS2 or SDK execution target actually consumed by the selected stub transport.

The same stub transports also expose execution outcomes:

```text
GET /unitree/execution-result
GET /unitree/execution-results
```

For the current plan-backed stubs, that outcome is `status=stub_emitted`.

The API also exposes the configured Unitree transport capability:

```text
GET /unitree/transport-capability
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
G1_BOBBY_UNITREE_STATE_CACHE_PATH=.runtime/unitree_state.json
G1_BOBBY_UNITREE_COMMAND_PLAN_CACHE_PATH=.runtime/unitree_command_plans.jsonl
```

The API writes the latest accepted Unitree snapshot to
`G1_BOBBY_UNITREE_STATE_CACHE_PATH`. On API process restart, it restores that
cached snapshot during startup so `/unitree/state`, `/state`, and operator
telemetry can recover immediately even before the next DDS post arrives.
It also restores the recent dry-run command-plan window from
`G1_BOBBY_UNITREE_COMMAND_PLAN_CACHE_PATH`, so `/unitree/command-plan` and
`/unitree/command-plans` do not go blank on a plain API restart.

Served `unitree_state` payloads include:

- `source=live` for snapshots received from the current DDS->API flow
- `source=restored` for snapshots loaded from cache during API startup
- `stale=true` when `timestamp_s` is older than `G1_BOBBY_UNITREE_STATE_TTL_S`

Served command-plan records include the same metadata surface:

- `source=live` for plans accepted in the current API process
- `source=restored` for plans reloaded from command-plan cache during startup
- `stale=true` when `recorded_at` is older than `G1_BOBBY_UNITREE_COMMAND_PLAN_TTL_S`

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
