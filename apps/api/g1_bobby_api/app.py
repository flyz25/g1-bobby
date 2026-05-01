from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated
from typing import Callable

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from g1_bobby_adapters import describe_unitree_transport_capability
from g1_bobby_contracts.events import StateEvent
from g1_bobby_contracts import (
    RejectedCommandRecord,
    UnitreeCommandPlanRecord,
    UnitreeExecutionPlanRecord,
    UnitreeExecutionResultRecord,
    UnitreeTransportCapability,
)
from g1_bobby_contracts.unitree import UnitreeDdsSnapshot

from .config import Settings
from .runtime import Runtime
from .websocket import router as websocket_router


def create_lifespan(settings: Settings) -> Callable:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.runtime = await Runtime.create(settings)
        yield
        await app.state.runtime.adapter.disconnect()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()
    app = FastAPI(
        title="G1 Bobby Teleop Spine",
        version="0.1.0",
        lifespan=create_lifespan(resolved_settings),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(websocket_router)

    def unitree_transport_capability_for_runtime() -> UnitreeTransportCapability | None:
        if str(app.state.settings.robot_adapter) != "unitree":
            return None
        return describe_unitree_transport_capability(app.state.settings.unitree_config())

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "online"}

    @app.get("/runtime")
    async def runtime_status() -> dict[str, object]:
        runtime = app.state.runtime
        transport_capability = unitree_transport_capability_for_runtime()
        return {
            "adapter": runtime.adapter_name,
            "safety": asdict(runtime.safety.limits),
            "command_gate": asdict(app.state.settings.command_gate_limits()),
            "accepted_commands": runtime.accepted_commands,
            "rejected_commands": runtime.rejected_commands,
            "active_operator_connected": runtime.active_operator_connected,
            "unitree_state": await runtime.unitree_state_status(),
            "unitree_command_plan": await runtime.unitree_command_plan_status(),
            "unitree_execution_plan": await runtime.unitree_execution_plan_status(),
            "unitree_execution_result": await runtime.unitree_execution_result_status(),
            "unitree_transport_capability": (
                transport_capability.model_dump(mode="json") if transport_capability is not None else None
            ),
            "rejected_command": await runtime.rejected_command_status(),
        }

    @app.get("/state")
    async def state() -> StateEvent:
        robot_state = await app.state.runtime.get_display_state()
        return StateEvent(
            state=robot_state,
            unitree_state=await app.state.runtime.get_unitree_state(),
        )

    @app.get("/unitree/state")
    async def unitree_state() -> UnitreeDdsSnapshot:
        snapshot = await app.state.runtime.get_unitree_state()
        if snapshot is None:
            raise HTTPException(status_code=404, detail="unitree state is not available")
        return snapshot

    @app.get("/unitree/command-plan")
    async def unitree_command_plan() -> UnitreeCommandPlanRecord:
        plan = await app.state.runtime.get_last_unitree_command_plan()
        if plan is None:
            raise HTTPException(status_code=404, detail="unitree command plan is not available")
        return plan

    @app.get("/unitree/command-plans")
    async def unitree_command_plans() -> list[UnitreeCommandPlanRecord]:
        return await app.state.runtime.get_unitree_command_plan_history()

    @app.get("/unitree/execution-plan")
    async def unitree_execution_plan() -> UnitreeExecutionPlanRecord:
        plan = await app.state.runtime.get_last_unitree_execution_plan()
        if plan is None:
            raise HTTPException(status_code=404, detail="unitree execution plan is not available")
        return plan

    @app.get("/unitree/execution-plans")
    async def unitree_execution_plans() -> list[UnitreeExecutionPlanRecord]:
        return await app.state.runtime.get_unitree_execution_plan_history()

    @app.get("/unitree/execution-result")
    async def unitree_execution_result() -> UnitreeExecutionResultRecord:
        result = await app.state.runtime.get_last_unitree_execution_result()
        if result is None:
            raise HTTPException(status_code=404, detail="unitree execution result is not available")
        return result

    @app.get("/unitree/execution-results")
    async def unitree_execution_results() -> list[UnitreeExecutionResultRecord]:
        return await app.state.runtime.get_unitree_execution_result_history()

    @app.get("/unitree/transport-capability")
    async def unitree_transport_capability() -> UnitreeTransportCapability:
        capability = unitree_transport_capability_for_runtime()
        if capability is None:
            raise HTTPException(status_code=404, detail="unitree transport capability is not available")
        return capability

    @app.get("/operator/rejection")
    async def rejected_command() -> RejectedCommandRecord:
        record = await app.state.runtime.get_last_rejected_command()
        if record is None:
            raise HTTPException(status_code=404, detail="rejected command is not available")
        return record

    @app.get("/operator/rejections")
    async def rejected_commands() -> list[RejectedCommandRecord]:
        return await app.state.runtime.get_rejected_command_history()

    @app.post("/unitree/state")
    async def ingest_unitree_state(
        snapshot: UnitreeDdsSnapshot,
        x_operator_token: Annotated[str | None, Header(alias="X-Operator-Token")] = None,
    ) -> dict[str, object]:
        if x_operator_token != app.state.settings.operator_token:
            raise HTTPException(status_code=401, detail="invalid operator token")

        await app.state.runtime.record_unitree_state(snapshot)
        return {
            "status": "accepted",
            "updates": app.state.runtime.unitree_state_updates,
            "snapshot_status": snapshot.status,
        }

    @app.post("/estop")
    async def estop() -> StateEvent:
        await app.state.runtime.adapter.emergency_stop()
        robot_state = await app.state.runtime.get_display_state()
        return StateEvent(
            state=robot_state,
            unitree_state=await app.state.runtime.get_unitree_state(),
        )

    @app.post("/reset-estop")
    async def reset_estop(
        x_operator_token: Annotated[str | None, Header(alias="X-Operator-Token")] = None,
    ) -> StateEvent:
        if x_operator_token != app.state.settings.operator_token:
            raise HTTPException(status_code=401, detail="invalid operator token")

        reset = await app.state.runtime.adapter.reset_emergency_stop()
        if not reset:
            raise HTTPException(status_code=409, detail="robot is not connected")
        robot_state = await app.state.runtime.get_display_state()
        return StateEvent(
            state=robot_state,
            unitree_state=await app.state.runtime.get_unitree_state(),
        )

    return app


app = create_app()
