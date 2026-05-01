from __future__ import annotations

import asyncio
from contextlib import suppress
from uuid import uuid4

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

from .command_gate import CommandGate

router = APIRouter()
command_adapter = TypeAdapter(CommandEnvelope)


async def send_event(websocket: WebSocket, event: object) -> None:
    await websocket.send_text(event.model_dump_json())


async def current_state_event(websocket: WebSocket) -> StateEvent:
    runtime = websocket.app.state.runtime
    return StateEvent(
        state=await runtime.get_display_state(),
        unitree_state=await runtime.get_unitree_state(),
    )


async def current_telemetry_event(websocket: WebSocket) -> TelemetryEvent:
    runtime = websocket.app.state.runtime
    return TelemetryEvent(
        state=await runtime.get_display_state(),
        accepted_commands=runtime.accepted_commands,
        rejected_commands=runtime.rejected_commands,
        unitree_state=await runtime.get_unitree_state(),
    )


@router.websocket("/ws/operator")
async def operator_socket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    settings = websocket.app.state.settings
    runtime = websocket.app.state.runtime
    session_id = str(uuid4())

    if token != settings.operator_token:
        await websocket.accept()
        runtime.record_rejected_command()
        await send_event(
            websocket,
            RejectEvent(code=ErrorCode.AUTH_FAILED, reason="invalid operator token"),
        )
        await websocket.close(code=1008)
        return

    await websocket.accept()
    if not await runtime.claim_operator_session(session_id):
        runtime.record_rejected_command()
        await send_event(
            websocket,
            RejectEvent(
                code=ErrorCode.SESSION_BUSY,
                reason="another operator session is already connected",
            ),
        )
        await websocket.close(code=1013)
        return

    command_gate = CommandGate(settings.command_gate_limits())
    telemetry_task = asyncio.create_task(send_telemetry(websocket))

    try:
        await send_event(websocket, await current_state_event(websocket))
        while True:
            message = await websocket.receive_json()
            try:
                command = command_adapter.validate_python(message)
            except ValidationError as exc:
                runtime.record_rejected_command()
                await send_event(
                    websocket,
                    RejectEvent(
                        seq=message.get("seq") if isinstance(message, dict) else None,
                        code=ErrorCode.INVALID_MESSAGE,
                        reason=exc.errors()[0]["msg"],
                    ),
                )
                continue

            gate_decision = command_gate.validate_and_record(command)
            if not gate_decision.accepted:
                runtime.record_rejected_command()
                await send_event(
                    websocket,
                    RejectEvent(
                        seq=command.seq,
                        code=gate_decision.code or ErrorCode.INVALID_MESSAGE,
                        reason=gate_decision.reason,
                    ),
                )
                continue

            state = await runtime.adapter.get_state()
            decision = runtime.safety.validate(command, state)
            if not decision.accepted:
                runtime.record_rejected_command()
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
                runtime.record_rejected_command()
                await send_event(
                    websocket,
                    RejectEvent(
                        seq=command.seq,
                        code=ErrorCode.EXECUTION_FAILED,
                        reason=str(exc),
                    ),
                )
                continue

            unitree_command_plan = await runtime.record_unitree_command_plan(command)
            runtime.record_accepted_command()
            await send_event(
                websocket,
                AckEvent(
                    seq=command.seq,
                    command_type=str(command.type),
                    unitree_command_plan=unitree_command_plan,
                ),
            )
    except WebSocketDisconnect:
        pass
    finally:
        telemetry_task.cancel()
        with suppress(asyncio.CancelledError):
            await telemetry_task
        await runtime.release_operator_session(session_id)


async def send_telemetry(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    while True:
        await asyncio.sleep(settings.telemetry_interval_s)
        await send_event(websocket, await current_telemetry_event(websocket))
