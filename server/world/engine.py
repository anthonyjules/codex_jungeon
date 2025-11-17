from __future__ import annotations

import asyncio
import random
import uuid
from typing import Dict, List, Optional

from ..models import (
    CharacterTemplate,
    GhostState,
    PlayerState,
    RoomDefinition,
    RoomState,
    WorldState,
    compose_room_description,
)
from ..services.persistence import PersistenceWorker
from .loader import WorldLoader
from .repository import WorldRepository


class WorldEngine:
    """Gameplay logic built on top of loaded world data."""

    def __init__(
        self,
        loader: WorldLoader,
        repository: WorldRepository,
        persistence: Optional[PersistenceWorker] = None,
    ) -> None:
        self.lock = asyncio.Lock()
        self.repository = repository
        self.persistence = persistence
        config, rooms_state, ghosts = loader.load()
        self.state = WorldState(config=config, rooms_state=rooms_state, ghosts=ghosts)
        self.repository.restore_state(self.state)

    def _schedule_persist_unlocked(self) -> None:
        payload = self.repository.build_save_payload(self.state)
        if self.persistence:
            self.persistence.schedule_save(payload)
        else:
            self.repository.write_save(payload)

    def _update_character_save_unlocked(self, player: PlayerState) -> None:
        self.state.character_saves[player.character_id] = player.create_save()

    async def allocate_player(self, character_id: str) -> PlayerState:
        async with self.lock:
            available = [
                c
                for c in self.state.config.characters.values()
                if c.id not in self.state.active_characters
            ]
            target: Optional[CharacterTemplate] = None
            for c in available:
                if c.id == character_id:
                    target = c
                    break
            if not target:
                raise ValueError("Character not available.")

            save = self.state.character_saves.get(character_id)
            if save:
                room_id = save.room_id
                coins = save.coins
                items = [
                    item_id
                    for item_id in save.items
                    if item_id in self.state.config.items
                ]
            else:
                room_id = target.starting_room
                coins = 0
                items = []
            if room_id not in self.state.rooms_state:
                room_id = next(iter(self.state.rooms_state.keys()))

            player_id = str(uuid.uuid4())
            player = PlayerState(
                player_id=player_id,
                character_id=target.id,
                name=target.name,
                room_id=room_id,
                coins=coins,
                items=list(items),
            )
            self.state.players[player_id] = player
            self.state.active_characters.add(target.id)
            room_state = self.state.rooms_state[player.room_id]
            room_state.players.add(player_id)
            self._update_character_save_unlocked(player)
            self._schedule_persist_unlocked()
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
            self._schedule_persist_unlocked()

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
            minimap = self._build_minimap_for_player(player_id)
            return {
                "roomId": room_def.id,
                "name": room_def.name,
                "description": description,
                "exits": list(room_def.exits.keys()),
                "coins": room_state.coins,
                "minimap": minimap,
                "characters": [
                    {
                        "name": self.state.players[pid].name,
                        "characterId": self.state.players[pid].character_id,
                    }
                    for pid in room_state.players
                    if pid != player_id
                ],
            }

    async def move_player(self, player_id: str, direction: str) -> Dict[str, object]:
        async with self.lock:
            player = self.state.players[player_id]
            room_def = self.state.config.rooms[player.room_id]
            dir_key = direction.lower()
            exit_def = room_def.exits.get(dir_key)
            if not exit_def:
                raise ValueError("You cannot go that way.")
            target_room_id = exit_def.target_room_id

            if exit_def.locked:
                has_key = False
                key_id = exit_def.key_id
                if key_id:
                    for item_id in player.items:
                        item = self.state.config.items.get(item_id)
                        if item and item.is_key and item.key_id == key_id:
                            has_key = True
                            break
                if not has_key:
                    raise ValueError("The door is locked. You need a key.")
                exit_def.locked = False
                new_room_for_lock = self.state.config.rooms[target_room_id]
                for back_dir, back_exit in new_room_for_lock.exits.items():
                    if (
                        back_exit.target_room_id == room_def.id
                        and back_exit.key_id == key_id
                    ):
                        back_exit.locked = False

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
            minimap = self._build_minimap_for_player(player_id)
            return {
                "roomId": new_room_def.id,
                "name": new_room_def.name,
                "description": description,
                "exits": list(new_room_def.exits.keys()),
                "coins": new_room_state.coins,
                "minimap": minimap,
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
            self._update_character_save_unlocked(player)
            self._schedule_persist_unlocked()
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
            self._update_character_save_unlocked(player)
            self._schedule_persist_unlocked()
            return {"dropped": amount, "roomCoins": room_state.coins}

    async def take_items(
        self, player_id: str, item_query: Optional[str]
    ) -> Dict[str, object]:
        async with self.lock:
            player = self.state.players[player_id]
            room_state = self.state.rooms_state[player.room_id]
            if not room_state.items:
                raise ValueError("There are no items to take.")

            taken_ids: List[str] = []
            query = (item_query or "").strip().lower()

            if not query or query == "all":
                taken_ids = list(room_state.items)
                room_state.items.clear()
            else:
                target_id: Optional[str] = None
                for item_id in room_state.items:
                    item = self.state.config.items.get(item_id)
                    if item and query in item.name.lower():
                        target_id = item_id
                        break
                if not target_id:
                    raise ValueError("You don't see that here.")
                room_state.items.remove(target_id)
                taken_ids.append(target_id)

            for item_id in taken_ids:
                player.items.append(item_id)

            taken_names: List[str] = []
            for item_id in taken_ids:
                item = self.state.config.items.get(item_id)
                if item:
                    taken_names.append(item.name)

            self._update_character_save_unlocked(player)
            self._schedule_persist_unlocked()
            return {"taken": taken_names, "count": len(taken_ids)}

    async def get_inventory(self, player_id: str) -> Dict[str, object]:
        async with self.lock:
            player = self.state.players[player_id]
            items = []
            for item_id in player.items:
                item = self.state.config.items.get(item_id)
                if item:
                    items.append({"id": item_id, "name": item.name})
            return {"coins": player.coins, "items": items}

    async def get_emote_message(self, player_id: str, verb: str) -> Optional[str]:
        async with self.lock:
            player = self.state.players.get(player_id)
            if not player:
                return None
            template = self.state.config.emotes.get(verb.lower())
            if not template:
                return None
            return f"{player.name} {template}"

    def _build_minimap_for_player(self, player_id: str) -> str:
        player = self.state.players.get(player_id)
        if not player:
            return ""

        room_def = self.state.config.rooms.get(player.room_id)
        room_state = self.state.rooms_state.get(player.room_id)
        if not room_def or not room_state:
            return ""

        width = 15
        height = 15
        grid: List[List[str]] = [[" " for _ in range(width)] for _ in range(height)]

        center_x = width // 2
        center_y = height // 2
        step = 4

        def draw_room_block(cx: int, cy: int, has_self: bool, has_other: bool) -> None:
            for dy in (-1, 0):
                for dx in (-1, 0):
                    x = cx + dx
                    y = cy + dy
                    if 0 <= x < width and 0 <= y < height:
                        if has_self:
                            ch = "*"
                        elif has_other:
                            ch = "P"
                        else:
                            ch = "."
                        grid[y][x] = ch

        players_here = room_state.players
        has_self = player_id in players_here
        has_other = any(pid != player_id for pid in players_here)

        draw_room_block(center_x, center_y, has_self=True, has_other=has_other)

        offsets = {
            "north": (0, -1),
            "south": (0, 1),
            "west": (-1, 0),
            "east": (1, 0),
        }

        for direction, exit_def in room_def.exits.items():
            offset = offsets.get(direction)
            if not offset:
                continue
            dx, dy = offset
            neighbour_id = exit_def.target_room_id
            neighbour_state = self.state.rooms_state.get(neighbour_id)
            cx = center_x + dx * step
            cy = center_y + dy * step

            if neighbour_state:
                neighbour_players = neighbour_state.players
                neighbour_has_other = any(pid != player_id for pid in neighbour_players)
                draw_room_block(cx, cy, has_self=False, has_other=neighbour_has_other)

            if dx == 0:
                link_x = center_x
                link_y = center_y + (dy * (step // 2))
                if 0 <= link_x < width and 0 <= link_y < height:
                    grid[link_y][link_x] = "|"
            else:
                link_x = center_x + (dx * (step // 2))
                link_y = center_y
                if 0 <= link_x < width and 0 <= link_y < height:
                    grid[link_y][link_x] = "-"

        return "\n".join("".join(row) for row in grid)

    async def move_ghosts_and_collect_events(self) -> Dict[str, List[str]]:
        async with self.lock:
            if not self.state.ghosts:
                return {}
            rng = random.Random()
            events: Dict[str, List[str]] = {}
            for ghost in self.state.ghosts.values():
                room_def = self.state.config.rooms.get(ghost.room_id)
                if not room_def or not room_def.exits:
                    continue
                exit_defs = list(room_def.exits.values())
                target_exit = rng.choice(exit_defs)
                ghost.room_id = target_exit.target_room_id

            for ghost in self.state.ghosts.values():
                for player in self.state.players.values():
                    if player.room_id == ghost.room_id:
                        msg = (
                            f"A ghost passes through the room: {ghost.description}."
                        )
                        events.setdefault(player.player_id, []).append(msg)
            return events
