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
