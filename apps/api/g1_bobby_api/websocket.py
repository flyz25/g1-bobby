from __future__ import annotations

import asyncio
from contextlib import suppress
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from g1_bobby_contracts import (
    AckEvent,
    CommandEnvelope,
    CommandPlanEvent,
    ExecutionPlanEvent,
    ExecutionResultEvent,
    ErrorCode,
    RejectedCommandEvent,
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
        reject_event = RejectEvent(code=ErrorCode.AUTH_FAILED, reason="invalid operator token")
        await runtime.record_rejected_command_event(reject_event)
        await send_event(
            websocket,
            reject_event,
        )
        await websocket.close(code=1008)
        return

    await websocket.accept()
    if not await runtime.claim_operator_session(session_id):
        reject_event = RejectEvent(
            code=ErrorCode.SESSION_BUSY,
            reason="another operator session is already connected",
        )
        await runtime.record_rejected_command_event(reject_event)
        await send_event(websocket, reject_event)
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
                reject_event = RejectEvent(
                    seq=message.get("seq") if isinstance(message, dict) else None,
                    code=ErrorCode.INVALID_MESSAGE,
                    reason=exc.errors()[0]["msg"],
                )
                await runtime.record_rejected_command_event(reject_event)
                await send_event(websocket, reject_event)
                continue

            gate_decision = command_gate.validate_and_record(command)
            if not gate_decision.accepted:
                reject_event = RejectEvent(
                    seq=command.seq,
                    code=gate_decision.code or ErrorCode.INVALID_MESSAGE,
                    reason=gate_decision.reason,
                )
                await runtime.record_rejected_command_event(reject_event, command_type=str(command.type))
                await send_event(websocket, reject_event)
                continue

            state = await runtime.adapter.get_state()
            decision = runtime.safety.validate(command, state)
            if not decision.accepted:
                reject_event = RejectEvent(
                    seq=command.seq,
                    code=ErrorCode.SAFETY_REJECTED,
                    reason=decision.reason,
                )
                await runtime.record_rejected_command_event(reject_event, command_type=str(command.type))
                await send_event(websocket, reject_event)
                continue

            try:
                await runtime.adapter.execute(command)
            except Exception as exc:  # pragma: no cover - future real adapter boundary
                unitree_execution_result = None
                consume_execution_result = getattr(runtime.adapter, "consume_last_execution_result", None)
                if callable(consume_execution_result):
                    execution_result = consume_execution_result()
                    if execution_result is not None:
                        unitree_execution_result = await runtime.record_unitree_execution_result(execution_result)
                reject_event = RejectEvent(
                    seq=command.seq,
                    code=ErrorCode.EXECUTION_FAILED,
                    reason=str(exc),
                    unitree_execution_result=unitree_execution_result,
                )
                await runtime.record_rejected_command_event(reject_event, command_type=str(command.type))
                await send_event(websocket, reject_event)
                continue

            unitree_command_plan = await runtime.record_unitree_command_plan(command)
            consume_execution_plan = getattr(runtime.adapter, "consume_last_execution_plan", None)
            unitree_execution_plan = None
            if callable(consume_execution_plan):
                execution_plan = consume_execution_plan()
                if execution_plan is not None:
                    unitree_execution_plan = await runtime.record_unitree_execution_plan(execution_plan)
            consume_execution_result = getattr(runtime.adapter, "consume_last_execution_result", None)
            unitree_execution_result = None
            if callable(consume_execution_result):
                execution_result = consume_execution_result()
                if execution_result is not None:
                    unitree_execution_result = await runtime.record_unitree_execution_result(execution_result)
            runtime.record_accepted_command()
            await send_event(
                websocket,
                AckEvent(
                    seq=command.seq,
                    command_type=str(command.type),
                    unitree_command_plan=unitree_command_plan,
                    unitree_execution_plan=unitree_execution_plan,
                    unitree_execution_result=unitree_execution_result,
                ),
            )
    except WebSocketDisconnect:
        pass
    finally:
        telemetry_task.cancel()
        with suppress(asyncio.CancelledError):
            await telemetry_task
        await runtime.release_operator_session(session_id)


@router.websocket("/ws/operator/audit")
async def operator_audit_socket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    after_id_raw = websocket.query_params.get("after_id")
    settings = websocket.app.state.settings
    runtime = websocket.app.state.runtime
    after_id = 0

    if after_id_raw is not None:
        try:
            after_id = max(int(after_id_raw), 0)
        except ValueError:
            await websocket.accept()
            reject_event = RejectEvent(code=ErrorCode.INVALID_MESSAGE, reason="after_id must be an integer")
            await runtime.record_rejected_command_event(reject_event)
            await send_event(websocket, reject_event)
            await websocket.close(code=1003)
            return

    if token != settings.operator_token:
        await websocket.accept()
        reject_event = RejectEvent(code=ErrorCode.AUTH_FAILED, reason="invalid operator token")
        await runtime.record_rejected_command_event(reject_event)
        await send_event(websocket, reject_event)
        await websocket.close(code=1008)
        return

    await websocket.accept()
    plan_subscription = await runtime.subscribe_unitree_command_plans()
    execution_plan_subscription = await runtime.subscribe_unitree_execution_plans()
    execution_result_subscription = await runtime.subscribe_unitree_execution_results()
    reject_subscription = await runtime.subscribe_rejected_commands()
    try:
        replay_events: list[tuple[float, object]] = []
        for record in await runtime.get_unitree_command_plan_history():
            if record.event_id > after_id:
                replay_events.append((record.recorded_at, CommandPlanEvent(unitree_command_plan=record)))
        for record in await runtime.get_rejected_command_history():
            if record.event_id > after_id:
                replay_events.append((record.recorded_at, RejectedCommandEvent(rejected_command=record)))
        for record in await runtime.get_unitree_execution_plan_history():
            if record.event_id > after_id:
                replay_events.append((record.recorded_at, ExecutionPlanEvent(unitree_execution_plan=record)))
        for record in await runtime.get_unitree_execution_result_history():
            if record.event_id > after_id:
                replay_events.append((record.recorded_at, ExecutionResultEvent(unitree_execution_result=record)))
        replay_events.sort(
            key=lambda item: (
                item[1].unitree_command_plan.event_id
                if isinstance(item[1], CommandPlanEvent)
                else (
                    item[1].unitree_execution_plan.event_id
                    if isinstance(item[1], ExecutionPlanEvent)
                    else (
                        item[1].unitree_execution_result.event_id
                        if isinstance(item[1], ExecutionResultEvent)
                        else item[1].rejected_command.event_id
                    )
                )
            )
        )

        for _, event in replay_events:
            await send_event(websocket, event)

        while True:
            plan_task = asyncio.create_task(plan_subscription.get())
            execution_plan_task = asyncio.create_task(execution_plan_subscription.get())
            execution_result_task = asyncio.create_task(execution_result_subscription.get())
            reject_task = asyncio.create_task(reject_subscription.get())
            done, pending = await asyncio.wait(
                {plan_task, execution_plan_task, execution_result_task, reject_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            for task in done:
                record = task.result()
                if task is plan_task:
                    await send_event(websocket, CommandPlanEvent(unitree_command_plan=record))
                elif task is execution_plan_task:
                    await send_event(websocket, ExecutionPlanEvent(unitree_execution_plan=record))
                elif task is execution_result_task:
                    await send_event(websocket, ExecutionResultEvent(unitree_execution_result=record))
                else:
                    await send_event(websocket, RejectedCommandEvent(rejected_command=record))
    except WebSocketDisconnect:
        pass
    finally:
        await runtime.unsubscribe_unitree_command_plans(plan_subscription)
        await runtime.unsubscribe_unitree_execution_plans(execution_plan_subscription)
        await runtime.unsubscribe_unitree_execution_results(execution_result_subscription)
        await runtime.unsubscribe_rejected_commands(reject_subscription)


async def send_telemetry(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    while True:
        await asyncio.sleep(settings.telemetry_interval_s)
        await send_event(websocket, await current_telemetry_event(websocket))
