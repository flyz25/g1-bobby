from __future__ import annotations

import asyncio
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from g1_bobby_contracts import (
    AckEvent,
    CommandEnvelope,
    ErrorCode,
    RejectEvent,
    StateEvent,
    TelemetryEvent,
)

router = APIRouter()
command_adapter = TypeAdapter(CommandEnvelope)


async def send_event(websocket: WebSocket, event: object) -> None:
    await websocket.send_text(event.model_dump_json())


@router.websocket("/ws/operator")
async def operator_socket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    settings = websocket.app.state.settings
    runtime = websocket.app.state.runtime

    if token != settings.operator_token:
        await websocket.accept()
        await send_event(
            websocket,
            RejectEvent(code=ErrorCode.AUTH_FAILED, reason="invalid operator token"),
        )
        await websocket.close(code=1008)
        return

    await websocket.accept()
    telemetry_task = asyncio.create_task(send_telemetry(websocket))

    try:
        await send_event(websocket, StateEvent(state=await runtime.adapter.get_state()))
        while True:
            message = await websocket.receive_json()
            try:
                command = command_adapter.validate_python(message)
            except ValidationError as exc:
                runtime.rejected_commands += 1
                await send_event(
                    websocket,
                    RejectEvent(
                        seq=message.get("seq") if isinstance(message, dict) else None,
                        code=ErrorCode.INVALID_MESSAGE,
                        reason=exc.errors()[0]["msg"],
                    ),
                )
                continue

            state = await runtime.adapter.get_state()
            decision = runtime.safety.validate(command, state)
            if not decision.accepted:
                runtime.rejected_commands += 1
                await send_event(
                    websocket,
                    RejectEvent(
                        seq=command.seq,
                        code=ErrorCode.SAFETY_REJECTED,
                        reason=decision.reason,
                    ),
                )
                continue

            try:
                await runtime.adapter.execute(command)
            except Exception as exc:  # pragma: no cover - future real adapter boundary
                runtime.rejected_commands += 1
                await send_event(
                    websocket,
                    RejectEvent(
                        seq=command.seq,
                        code=ErrorCode.EXECUTION_FAILED,
                        reason=str(exc),
                    ),
                )
                continue

            await send_event(websocket, AckEvent(seq=command.seq, command_type=str(command.type)))
    except WebSocketDisconnect:
        pass
    finally:
        telemetry_task.cancel()
        with suppress(asyncio.CancelledError):
            await telemetry_task


async def send_telemetry(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    runtime = websocket.app.state.runtime
    while True:
        await asyncio.sleep(settings.telemetry_interval_s)
        await send_event(
            websocket,
            TelemetryEvent(
                state=await runtime.adapter.get_state(),
                accepted_commands=len(runtime.adapter.accepted_commands),
                rejected_commands=runtime.rejected_commands,
            ),
        )

