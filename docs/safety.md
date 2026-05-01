# Safety Model

The MVP is fail-closed.

Movement commands are rejected unless all conditions are true:

- command sequence number is increasing
- command timestamp is fresh and not too far in the future
- operator socket is within rate limits
- robot is connected
- e-stop is clear
- robot mode is `manual`
- robot state is fresh
- operator heartbeat is fresh
- obstacle distance is known
- obstacle distance is at least `0.5m`
- velocity values are within safety limits

`stop`, `estop`, and `heartbeat` are accepted even when normal movement checks fail.

## Initial Limits

- max linear velocity: `0.35`
- max angular velocity: `0.6`
- state TTL: `1s`
- heartbeat TTL: `2s`
- minimum obstacle distance: `0.5m`
- max command age: `1s`
- future command tolerance: `0.25s`
- max command rate: `20 commands/s`

These values are conservative placeholders for laptop/mock development. Real robot integration must revisit them with hardware-specific data.
