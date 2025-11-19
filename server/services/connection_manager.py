from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from fastapi import WebSocket

from ..world.engine import WorldEngine


@dataclass
class BroadcastEvent:
    player_id: str
    text: str
    include_self: bool = False


class ConnectionManager:
    """Track active websocket connections per player."""

    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}

    def attach(self, player_id: str, ws: WebSocket) -> None:
        self._connections[player_id] = ws

    def detach(self, player_id: str) -> None:
        self._connections.pop(player_id, None)

    def get(self, player_id: str) -> WebSocket | None:
        return self._connections.get(player_id)

    def get_all_connected_player_ids(self) -> list[str]:
        """Return a list of all currently connected player IDs."""
        return list(self._connections.keys())

    async def send(self, player_id: str, message: Dict[str, object]) -> None:
        ws = self._connections.get(player_id)
        if not ws:
            return
        try:
            await ws.send_json(message)
        except RuntimeError:
            # Connection cleanup happens on disconnect.
            pass

    async def send_to_all(self, message: Dict[str, object]) -> None:
        """Send a message to all connected players."""
        for player_id in self._connections.keys():
            await self.send(player_id, message)

    async def broadcast_room_event(
        self, world: WorldEngine, event: BroadcastEvent
    ) -> None:
        player = await world.get_player(event.player_id)
        if not player:
            return
        player_ids = await world.get_room_player_ids(player.room_id)
        payload = {"type": "event", "data": {"text": event.text}}
        for pid in player_ids:
            if not event.include_self and pid == event.player_id:
                continue
            ws = self._connections.get(pid)
            if not ws:
                continue
            try:
                await ws.send_json(payload)
            except RuntimeError:
                continue
