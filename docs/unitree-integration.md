# Unitree Integration Boundary

`UnitreeAdapter` is intentionally unimplemented in the MVP.

The future adapter must satisfy the same interface as `MockRobotAdapter`:

- `connect()`
- `disconnect()`
- `get_state()`
- `execute(command)`
- `emergency_stop()`

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

