from __future__ import annotations

from fastapi import WebSocket, WebSocketDisconnect

from ..commands.parser import parse_command_input
from ..commands.router import CommandRouter
from ..schemas import CommandMessage, ServerMessage
from ..services.connection_manager import ConnectionManager
from ..services.game_service import GameService
from ..world.engine import WorldEngine


async def send_room_state(ws: WebSocket, game: GameService, player_id: str) -> None:
    room_info = await game.describe_room(player_id)
    await ws.send_json(ServerMessage(type="roomState", data=room_info).model_dump())


async def send_inventory(ws: WebSocket, game: GameService, player_id: str) -> None:
    inventory = await game.get_inventory(player_id)
    await ws.send_json(ServerMessage(type="inventory", data=inventory).model_dump())


def create_websocket_endpoint(
    game: GameService,
    world: WorldEngine,
    connections: ConnectionManager,
):
    router = CommandRouter(world, connections)

    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        session_id = ws.query_params.get("sessionId")
        if not session_id:
            await ws.close()
            return
        session = game.get_session(session_id)
        if not session:
            await ws.close()
            return
        player_id = session.player_id
        connections.attach(player_id, ws)

        await send_room_state(ws, game, player_id)
        await send_inventory(ws, game, player_id)

        try:
            while True:
                raw = await ws.receive_json()
                msg = CommandMessage.model_validate(raw)
                if msg.type != "command" or msg.input is None:
                    continue
                parsed = parse_command_input(msg.input)
                try:
                    result = await router.dispatch(player_id, parsed)
                    for reply in result.replies:
                        await ws.send_json(reply.model_dump())
                    if result.refresh_room:
                        await send_room_state(ws, game, player_id)
                    if result.refresh_inventory:
                        await send_inventory(ws, game, player_id)
                    for event in result.broadcasts:
                        await connections.broadcast_room_event(world, event)
                except ValueError as exc:
                    await ws.send_json(
                        ServerMessage(
                            type="error",
                            data={"message": str(exc)},
                        ).model_dump()
                    )
        except WebSocketDisconnect:
            await game.release_player(player_id)
            game.remove_session(session_id)
            connections.detach(player_id)

    return websocket_endpoint
