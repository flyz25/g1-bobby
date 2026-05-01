from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from g1_bobby_contracts.events import StateEvent

from .config import Settings
from .runtime import Runtime
from .websocket import router as websocket_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = Settings()
    app.state.runtime = await Runtime.create()
    yield
    await app.state.runtime.adapter.disconnect()


def create_app() -> FastAPI:
    app = FastAPI(
        title="G1 Bobby Teleop Spine",
        version="0.1.0",
        lifespan=lifespan,
    )
    settings = Settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(websocket_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "online"}

    @app.get("/state")
    async def state() -> StateEvent:
        robot_state = await app.state.runtime.adapter.get_state()
        return StateEvent(state=robot_state)

    @app.post("/estop")
    async def estop() -> StateEvent:
        await app.state.runtime.adapter.emergency_stop()
        robot_state = await app.state.runtime.adapter.get_state()
        return StateEvent(state=robot_state)

    @app.post("/reset-estop")
    async def reset_estop() -> StateEvent:
        reset = await app.state.runtime.adapter.reset_emergency_stop()
        if not reset:
            raise HTTPException(status_code=409, detail="robot is not connected")
        robot_state = await app.state.runtime.adapter.get_state()
        return StateEvent(state=robot_state)

    return app


app = create_app()

