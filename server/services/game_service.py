from __future__ import annotations

import uuid
from typing import Optional, Tuple

from ..models import PlayerState
from ..sessions import Session, SessionManager
from ..world.engine import WorldEngine


class GameService:
    """High-level facade exposing operations used by HTTP and websocket layers."""

    def __init__(self, world: WorldEngine, sessions: SessionManager) -> None:
        self.world = world
        self.sessions = sessions

    async def list_available_characters(self):
        return await self.world.get_available_characters()

    async def login(self, character_id: str) -> Tuple[str, PlayerState]:
        player = await self.world.allocate_player(character_id)
        session_id = str(uuid.uuid4())
        self.sessions.create_session(session_id, player.player_id)
        return session_id, player

    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get_session(session_id)

    def remove_session(self, session_id: str) -> None:
        self.sessions.remove_session(session_id)

    async def release_player(self, player_id: str) -> None:
        await self.world.release_player(player_id)

    async def describe_room(self, player_id: str):
        return await self.world.describe_room_for_player(player_id)

    async def get_inventory(self, player_id: str):
        return await self.world.get_inventory(player_id)

    async def get_online_player_names(self, player_ids: list[str]) -> list[dict[str, str]]:
        """Get names for a list of player IDs. Returns list of dicts with 'playerId' and 'name'."""
        result = []
        for pid in player_ids:
            player = await self.world.get_player(pid)
            if player:
                result.append({"playerId": pid, "name": player.name})
        return result
