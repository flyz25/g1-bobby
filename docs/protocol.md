# Operator Protocol

All operator traffic uses WebSocket JSON.

Endpoint:

```text
ws://localhost:8010/ws/operator?token=dev-operator-token
```

## Client Command Envelope

```json
{
  "type": "heartbeat",
  "seq": 1,
  "timestamp": 1760000000.0,
  "payload": {}
}
```

Common fields:

- `type`: command type.
- `seq`: client sequence number. It must increase within a WebSocket session.
- `timestamp`: Unix timestamp from client.
- `payload`: type-specific object.

The server rejects stale, future-dated, replayed, and rate-limited commands
before safety validation. Defaults:

- max command age: `1.0s`
- future timestamp tolerance: `0.25s`
- max commands per second per operator socket: `20`

## Commands

### `heartbeat`

```json
{
  "type": "heartbeat",
  "seq": 1,
  "timestamp": 1760000000.0,
  "payload": {
    "client_id": "quest-dev"
  }
}
```

### `set_mode`

Modes: `idle`, `manual`, `assist`.

```json
{
  "type": "set_mode",
  "seq": 2,
  "timestamp": 1760000001.0,
  "payload": {
    "mode": "manual"
  }
}
```

### `move_velocity`

```json
{
  "type": "move_velocity",
  "seq": 3,
  "timestamp": 1760000002.0,
  "payload": {
    "linear_x": 0.1,
    "linear_y": 0.0,
    "angular_z": 0.0,
    "duration_ms": 100
  }
}
```

### `stop`

```json
{
  "type": "stop",
  "seq": 4,
  "timestamp": 1760000003.0,
  "payload": {
    "reason": "operator_stop"
  }
}
```

### `estop`

```json
{
  "type": "estop",
  "seq": 5,
  "timestamp": 1760000004.0,
  "payload": {
    "reason": "operator_estop"
  }
}
```

## Server Events

### `ack`

```json
{
  "type": "ack",
  "seq": 3,
  "command_type": "move_velocity",
  "message": "accepted"
}
```

### `reject`

```json
{
  "type": "reject",
  "seq": 3,
  "code": "safety_rejected",
  "reason": "operator heartbeat is stale"
}
```

Reject codes:

- `auth_failed`
- `invalid_message`
- `rate_limited`
- `replayed_command`
- `safety_rejected`
- `session_busy`
- `stale_command`
- `execution_failed`

### `state` and `telemetry`

State events include current robot state. Telemetry also includes accepted and rejected command counters.
