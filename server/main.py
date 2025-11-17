from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api.http import create_http_router
from .api.ws import create_websocket_endpoint
from .schemas import ServerMessage
from .services.connection_manager import ConnectionManager
from .services.game_service import GameService
from .services.persistence import PersistenceWorker
from .sessions import SessionManager
from .world import WorldEngine, WorldLoader, WorldRepository


BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_DIR = BASE_DIR / "client"
DATA_DIR = BASE_DIR / "data"

app = FastAPI(title="Jungeon MUD")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

loader = WorldLoader(DATA_DIR)
repository = WorldRepository(DATA_DIR / "savegame.json")
persistence = PersistenceWorker(repository)
world = WorldEngine(loader, repository, persistence)
sessions = SessionManager()
connections = ConnectionManager()
game_service = GameService(world, sessions)

app.include_router(create_http_router(game_service))

websocket_endpoint = create_websocket_endpoint(game_service, world, connections)
app.websocket("/ws")(websocket_endpoint)


@app.get("/", response_class=HTMLResponse)
async def index() -> Any:
    return FileResponse(CLIENT_DIR / "index.html")


app.mount(
    "/static",
    StaticFiles(directory=str(CLIENT_DIR)),
    name="static",
)


@app.on_event("startup")
async def start_background_tasks() -> None:
    async def ghost_worker() -> None:
        await asyncio.sleep(3)
        while True:
            await asyncio.sleep(random.uniform(8, 20))
            events = await world.move_ghosts_and_collect_events()
            if not events:
                continue
            for pid, texts in events.items():
                for text in texts:
                    await connections.send(
                        pid,
                        ServerMessage(
                            type="event",
                            data={"text": text},
                        ).model_dump(),
                    )

    asyncio.create_task(ghost_worker())
