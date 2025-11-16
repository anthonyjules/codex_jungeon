from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .sessions import SessionManager
from .world import World


BASE_DIR = Path(__file__).resolve().parent.parent
CLIENT_DIR = BASE_DIR / "client"


app = FastAPI(title="Jungeon MUD")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

world = World()
sessions = SessionManager()
connections: dict[str, WebSocket] = {}


class CharacterInfo(BaseModel):
    id: str
    name: str
    shortDescription: str


class AvailableCharactersResponse(BaseModel):
    characters: List[CharacterInfo]


class LoginRequest(BaseModel):
    characterId: str


class LoginResponse(BaseModel):
    sessionId: str
    playerName: str
    characterId: str


@app.get("/", response_class=HTMLResponse)
async def index() -> Any:
    return FileResponse(CLIENT_DIR / "index.html")


app.mount(
    "/static",
    StaticFiles(directory=str(CLIENT_DIR)),
    name="static",
)


@app.get("/api/characters/available", response_model=AvailableCharactersResponse)
async def get_available_characters() -> AvailableCharactersResponse:
    characters = await world.get_available_characters()
    return AvailableCharactersResponse(
        characters=[
            CharacterInfo(
                id=c.id,
                name=c.name,
                shortDescription=c.short_description,
            )
            for c in characters
        ]
    )


@app.post("/api/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    player = await world.allocate_player(req.characterId)
    session_id = str(uuid.uuid4())
    sessions.create_session(session_id, player.player_id)
    return LoginResponse(
        sessionId=session_id,
        playerName=player.name,
        characterId=player.character_id,
    )


class CommandMessage(BaseModel):
    type: str
    input: Optional[str] = None


class ServerMessage(BaseModel):
    type: str
    data: Dict[str, Any]


async def send_room_state(ws: WebSocket, player_id: str) -> None:
    room_info = await world.describe_room_for_player(player_id)
    await ws.send_json(
        ServerMessage(type="roomState", data=room_info).model_dump()
    )
    inventory = await world.get_inventory(player_id)
    await ws.send_json(
        ServerMessage(type="inventory", data=inventory).model_dump()
    )


def parse_command_input(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {"action": "noop"}
    if text.startswith("/"):
        verb = text[1:].strip().lower()
        return {"action": "emote", "verb": verb}
    parts = text.split()
    if not parts:
        return {"action": "noop"}
    verb = parts[0].lower()
    args = parts[1:]
    return {"action": verb, "args": args}


async def broadcast_event_to_room(
    player_id: str, text: str, include_self: bool = False
) -> None:
    player = await world.get_player(player_id)
    if not player:
        return
    player_ids = await world.get_room_player_ids(player.room_id)
    message = ServerMessage(type="event", data={"text": text}).model_dump()
    for pid in player_ids:
        if not include_self and pid == player_id:
            continue
        ws = connections.get(pid)
        if ws is None:
            continue
        try:
            await ws.send_json(message)
        except RuntimeError:
            # Ignore send errors; connection cleanup happens on disconnect.
            continue


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    session_id = ws.query_params.get("sessionId")
    if not session_id:
        await ws.close()
        return
    session = sessions.get_session(session_id)
    if not session:
        await ws.close()
        return
    player_id = session.player_id

    connections[player_id] = ws

    await send_room_state(ws, player_id)

    try:
        while True:
            raw = await ws.receive_json()
            msg = CommandMessage.model_validate(raw)
            if msg.type != "command" or msg.input is None:
                continue
            parsed = parse_command_input(msg.input)
            action = parsed.get("action")
            try:
                if action == "noop":
                    continue
                elif action == "go":
                    args = parsed.get("args") or []
                    if not args:
                        raise ValueError("Specify a direction (north/south/east/west).")
                    direction = args[0]
                    room_info = await world.move_player(player_id, direction)
                    await broadcast_event_to_room(
                        player_id, f"You hear footsteps as someone moves.", include_self=False
                    )
                    await ws.send_json(
                        ServerMessage(
                            type="roomState",
                            data=room_info,
                        ).model_dump()
                    )
                elif action == "collect":
                    info = await world.collect_coins(player_id)
                    await broadcast_event_to_room(
                        player_id,
                        "Someone collects coins nearby.",
                        include_self=False,
                    )
                    await ws.send_json(
                        ServerMessage(
                            type="event",
                            data={"text": f"You collect {info['collected']} coin(s)."},
                        ).model_dump()
                    )
                    await send_room_state(ws, player_id)
                elif action == "drop":
                    info = await world.drop_coins(player_id)
                    await broadcast_event_to_room(
                        player_id,
                        "You hear coins clatter onto the floor.",
                        include_self=False,
                    )
                    await ws.send_json(
                        ServerMessage(
                            type="event",
                            data={"text": f"You drop {info['dropped']} coin(s)."},
                        ).model_dump()
                    )
                    await send_room_state(ws, player_id)
                elif action == "look":
                    await send_room_state(ws, player_id)
                elif action == "emote":
                    verb = parsed.get("verb")
                    if not verb:
                        raise ValueError("Specify an emote, e.g. /sneeze.")
                    emote_text = await world.get_emote_message(player_id, verb)
                    if not emote_text:
                        raise ValueError("Unknown emote.")
                    await ws.send_json(
                        ServerMessage(
                            type="event",
                            data={"text": f"You {emote_text.split(' ', 1)[1]}"},
                        ).model_dump()
                    )
                    await broadcast_event_to_room(player_id, emote_text, include_self=False)
                elif action == "say":
                    args = parsed.get("args") or []
                    if not args:
                        raise ValueError("Say what?")
                    text = " ".join(args)
                    player = await world.get_player(player_id)
                    speaker_name = player.name if player else "Someone"
                    await ws.send_json(
                        ServerMessage(
                            type="event",
                            data={"text": f'You say: "{text}"'},
                        ).model_dump()
                    )
                    await broadcast_event_to_room(
                        player_id,
                        f'{speaker_name} says: "{text}"',
                        include_self=False,
                    )
                else:
                    await ws.send_json(
                        ServerMessage(
                            type="error",
                            data={"message": f"Unknown command: {action}"},
                        ).model_dump()
                    )
            except ValueError as e:
                await ws.send_json(
                    ServerMessage(
                        type="error",
                        data={"message": str(e)},
                    ).model_dump()
                )
    except WebSocketDisconnect:
        await world.release_player(player_id)
        sessions.remove_session(session_id)
        connections.pop(player_id, None)
