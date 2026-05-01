# Architecture

## MVP Flow

```text
Quest / operator client
  -> WebSocket JSON
  -> FastAPI gateway
  -> command schema validation
  -> fail-closed safety validator
  -> mock robot adapter
  -> telemetry/state events
```

## Runtime Components

- `apps/api`: FastAPI HTTP and WebSocket server.
- `packages/contracts`: Pydantic command, event, and state schemas.
- `packages/safety`: safety decision engine.
- `packages/robot_adapters`: mock adapter now, real Unitree adapter later.

## Deferred

- Real Unitree SDK calls.
- Native ROS2 action/topic publishing.
- Quest/Unity implementation.
- WebRTC video pipeline.
- Ollama/Whisper/vision AI.

