from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .models import (
    CharacterTemplate,
    PlayerState,
    RoomDefinition,
    RoomObject,
    RoomState,
    WorldConfig,
    WorldState,
    compose_room_description,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class World:
    """In-memory world manager. Single-process, guarded by a lock."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.state = self._load_initial_state()

    def _load_initial_state(self) -> WorldState:
        with open(DATA_DIR / "world.json", "r", encoding="utf-8") as f:
            world_data = json.load(f)
        with open(DATA_DIR / "characters.json", "r", encoding="utf-8") as f:
            chars_data = json.load(f)
        with open(DATA_DIR / "verbs.json", "r", encoding="utf-8") as f:
            verbs_data = json.load(f)

        rooms: Dict[str, RoomDefinition] = {}
        rooms_state: Dict[str, RoomState] = {}
        for r in world_data.get("rooms", []):
            objects: List[RoomObject] = []
            for o in r.get("objects", []):
                objects.append(
                    RoomObject(
                        id=o["id"],
                        name=o["name"],
                        description=o.get("description", ""),
                        verbs=o.get("verbs", []),
                        state=o.get("state", "idle"),
                    )
                )
            room_def = RoomDefinition(
                id=r["id"],
                name=r["name"],
                description=r["description"],
                exits=r.get("exits", {}),
                coins_initial=r.get("coins", {}).get("initial", 0),
                coins_respawn=r.get("coins", {}).get("respawn", {}),
                objects=objects,
                appearance=r.get("appearance", {}),
            )
            rooms[room_def.id] = room_def
            rooms_state[room_def.id] = RoomState(
                id=room_def.id,
                coins=room_def.coins_initial,
                objects_state={o.id: o.state for o in objects},
            )

        characters: Dict[str, CharacterTemplate] = {}
        for c in chars_data.get("characters", []):
            characters[c["id"]] = CharacterTemplate(
                id=c["id"],
                name=c["name"],
                short_description=c["shortDescription"],
                long_description=c["longDescription"],
                starting_room=c["startingRoom"],
                appearance_in_room=c["appearanceInRoom"],
            )

        emotes = verbs_data.get("emotes", {})
        allowed_object_verbs = verbs_data.get("objectVerbs", [])

        config = WorldConfig(
            rooms=rooms,
            characters=characters,
            emotes=emotes,
            allowed_object_verbs=allowed_object_verbs,
        )

        return WorldState(config=config, rooms_state=rooms_state)

    async def allocate_player(self, character_id: str) -> PlayerState:
        async with self.lock:
            if character_id in self.state.active_characters:
                raise ValueError("Character already in use")
            character = self.state.config.characters[character_id]
            player_id = str(uuid.uuid4())
            player = PlayerState(
                player_id=player_id,
                character_id=character.id,
                name=character.name,
                room_id=character.starting_room,
            )
            self.state.players[player_id] = player
            self.state.active_characters.add(character.id)
            room_state = self.state.rooms_state[player.room_id]
            room_state.players.add(player_id)
            return player

    async def release_player(self, player_id: str) -> None:
        async with self.lock:
            player = self.state.players.pop(player_id, None)
            if not player:
                return
            self.state.active_characters.discard(player.character_id)
            room_state = self.state.rooms_state.get(player.room_id)
            if room_state:
                room_state.players.discard(player_id)

    async def get_available_characters(self) -> List[CharacterTemplate]:
        async with self.lock:
            return [
                c
                for c in self.state.config.characters.values()
                if c.id not in self.state.active_characters
            ]

    async def get_player(self, player_id: str) -> Optional[PlayerState]:
        async with self.lock:
            return self.state.players.get(player_id)

    async def get_room_player_ids(self, room_id: str) -> List[str]:
        async with self.lock:
            room = self.state.rooms_state.get(room_id)
            if not room:
                return []
            return list(room.players)

    async def describe_room_for_player(self, player_id: str) -> Dict[str, object]:
        async with self.lock:
            player = self.state.players[player_id]
            room_def = self.state.config.rooms[player.room_id]
            room_state = self.state.rooms_state[player.room_id]
            player_states = [
                self.state.players[pid]
                for pid in room_state.players
                if pid != player_id
            ]
            description = compose_room_description(
                room_def, room_state, player_states, self.state.config
            )
            return {
                "roomId": room_def.id,
                "name": room_def.name,
                "description": description,
                "exits": list(room_def.exits.keys()),
                "coins": room_state.coins,
                "characters": [
                    {
                        "name": self.state.players[pid].name,
                        "characterId": self.state.players[pid].character_id,
                    }
                    for pid in room_state.players
                    if pid != player_id
                ],
            }

    async def move_player(
        self, player_id: str, direction: str
    ) -> Dict[str, object]:
        async with self.lock:
            player = self.state.players[player_id]
            room_def = self.state.config.rooms[player.room_id]
            target_room_id = room_def.exits.get(direction.lower())
            if not target_room_id:
                raise ValueError("You cannot go that way.")
            old_room_state = self.state.rooms_state[player.room_id]
            new_room_def = self.state.config.rooms[target_room_id]
            new_room_state = self.state.rooms_state[target_room_id]

            old_room_state.players.discard(player_id)
            new_room_state.players.add(player_id)
            player.room_id = target_room_id

            player_states = [
                self.state.players[pid]
                for pid in new_room_state.players
                if pid != player_id
            ]
            description = compose_room_description(
                new_room_def, new_room_state, player_states, self.state.config
            )
            return {
                "roomId": new_room_def.id,
                "name": new_room_def.name,
                "description": description,
                "exits": list(new_room_def.exits.keys()),
                "coins": new_room_state.coins,
                "characters": [
                    {
                        "name": self.state.players[pid].name,
                        "characterId": self.state.players[pid].character_id,
                    }
                    for pid in new_room_state.players
                    if pid != player_id
                ],
            }

    async def collect_coins(self, player_id: str) -> Dict[str, int]:
        async with self.lock:
            player = self.state.players[player_id]
            room_state = self.state.rooms_state[player.room_id]
            if room_state.coins <= 0:
                raise ValueError("There are no coins to collect.")
            amount = room_state.coins
            room_state.coins = 0
            player.coins += amount
            return {"collected": amount, "playerCoins": player.coins}

    async def drop_coins(self, player_id: str) -> Dict[str, int]:
        async with self.lock:
            player = self.state.players[player_id]
            if player.coins <= 0:
                raise ValueError("You have no coins to drop.")
            amount = player.coins
            player.coins = 0
            room_state = self.state.rooms_state[player.room_id]
            room_state.coins += amount
            return {"dropped": amount, "roomCoins": room_state.coins}

    async def get_inventory(self, player_id: str) -> Dict[str, int]:
        async with self.lock:
            player = self.state.players[player_id]
            return {"coins": player.coins}

    async def get_emote_message(self, player_id: str, verb: str) -> Optional[str]:
        async with self.lock:
            player = self.state.players.get(player_id)
            if not player:
                return None
            template = self.state.config.emotes.get(verb.lower())
            if not template:
                return None
            return f"{player.name} {template}"

