from __future__ import annotations

import asyncio
import json
import random
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .models import (
    CharacterSave,
    CharacterTemplate,
    ExitDefinition,
    GhostState,
    ItemDefinition,
    PlayerState,
    RoomDefinition,
    RoomObject,
    RoomState,
    WorldConfig,
    WorldState,
    compose_room_description,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAVE_FILE = DATA_DIR / "savegame.json"


class World:
    """In-memory world manager. Single-process, guarded by a lock."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.state = self._load_initial_state()
        self._load_saved_state()

    def _load_saved_state(self) -> None:
        """Load persisted room, character, and ghost state if available."""
        if not SAVE_FILE.exists():
            return
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        rooms_data = data.get("rooms", {})
        for room_id, raw in rooms_data.items():
            room_state = self.state.rooms_state.get(room_id)
            if not room_state:
                continue
            if isinstance(raw.get("coins"), int):
                room_state.coins = raw["coins"]
            if isinstance(raw.get("items"), list):
                room_state.items = [
                    item_id
                    for item_id in raw["items"]
                    if item_id in self.state.config.items
                ]

        characters_data = data.get("characters", {})
        for char_id, raw in characters_data.items():
            room_id = raw.get("roomId")
            if room_id not in self.state.rooms_state:
                room_id = next(iter(self.state.rooms_state.keys()))
            coins = int(raw.get("coins", 0))
            items = [
                item_id
                for item_id in raw.get("items", [])
                if item_id in self.state.config.items
            ]
            self.state.character_saves[char_id] = CharacterSave(
                character_id=char_id,
                room_id=room_id,
                coins=coins,
                items=items,
            )

        ghosts_data = data.get("ghosts", {})
        for ghost_id, raw in ghosts_data.items():
            ghost_state = self.state.ghosts.get(ghost_id)
            if not ghost_state:
                continue
            room_id = raw.get("roomId")
            if room_id in self.state.rooms_state:
                ghost_state.room_id = room_id

    def _save_state_unlocked(self) -> None:
        """Persist dynamic world and character state to disk."""
        data = {
            "rooms": {
                room_id: {
                    "coins": room_state.coins,
                    "items": list(room_state.items),
                }
                for room_id, room_state in self.state.rooms_state.items()
            },
            "characters": {
                char_id: {
                    "roomId": cs.room_id,
                    "coins": cs.coins,
                    "items": list(cs.items),
                }
                for char_id, cs in self.state.character_saves.items()
            },
            "ghosts": {
                ghost_id: {"roomId": ghost.room_id}
                for ghost_id, ghost in self.state.ghosts.items()
            },
        }
        try:
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            # Ignore persistence errors in the game loop.
            return

    def _update_character_save_unlocked(self, player: PlayerState) -> None:
        self.state.character_saves[player.character_id] = CharacterSave(
            character_id=player.character_id,
            room_id=player.room_id,
            coins=player.coins,
            items=list(player.items),
        )

    def _load_initial_state(self) -> WorldState:
        with open(DATA_DIR / "world.json", "r", encoding="utf-8") as f:
            world_data = json.load(f)
        with open(DATA_DIR / "characters.json", "r", encoding="utf-8") as f:
            chars_data = json.load(f)
        with open(DATA_DIR / "verbs.json", "r", encoding="utf-8") as f:
            verbs_data = json.load(f)

        # Characters
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

        # Rooms, items, ghosts – either loaded from JSON or, if requested,
        # procedurally generated and then written back to JSON so the
        # resulting world is explicit.
        if world_data.get("procedural"):
            rooms, rooms_state, items, ghosts = self._generate_procedural_world(
                world_data
            )
            world_name = world_data.get("worldName") or "The Jungeon"
            self._write_world_definition(world_name, rooms, rooms_state, items, ghosts)
        else:
            rooms, rooms_state, items, ghosts = self._load_rooms_from_json(world_data)

        emotes = verbs_data.get("emotes", {})
        allowed_object_verbs = verbs_data.get("objectVerbs", [])

        config = WorldConfig(
            rooms=rooms,
            characters=characters,
            items=items,
            emotes=emotes,
            allowed_object_verbs=allowed_object_verbs,
        )

        return WorldState(config=config, rooms_state=rooms_state, ghosts=ghosts)

    def _load_rooms_from_json(
        self, world_data: Dict[str, object]
    ) -> Tuple[
        Dict[str, RoomDefinition],
        Dict[str, RoomState],
        Dict[str, ItemDefinition],
        Dict[str, GhostState],
    ]:
        rooms: Dict[str, RoomDefinition] = {}
        rooms_state: Dict[str, RoomState] = {}
        items: Dict[str, ItemDefinition] = {}
        ghosts: Dict[str, GhostState] = {}

        items_data = world_data.get("items", {})
        for item_id, raw in items_data.items():
            items[item_id] = ItemDefinition(
                id=item_id,
                name=raw.get("name", item_id),
                description=raw.get("description", ""),
                is_key=bool(raw.get("isKey", False)),
                key_id=raw.get("keyId"),
            )

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

            exits_raw = r.get("exits", {})
            exits: Dict[str, ExitDefinition] = {}
            for direction, value in exits_raw.items():
                if isinstance(value, str):
                    exits[direction] = ExitDefinition(
                        direction=direction,
                        target_room_id=value,
                        locked=False,
                        key_id=None,
                    )
                elif isinstance(value, dict):
                    exits[direction] = ExitDefinition(
                        direction=direction,
                        target_room_id=value.get("target", ""),
                        locked=bool(value.get("locked", False)),
                        key_id=value.get("keyId"),
                    )

            room_def = RoomDefinition(
                id=r["id"],
                name=r["name"],
                description=r["description"],
                exits=exits,
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
            room_items = [
                item_id
                for item_id in r.get("items", [])
                if item_id in items
            ]
            rooms_state[room_def.id].items.extend(room_items)

        ghosts_data = world_data.get("ghosts", {})
        for ghost_id, raw in ghosts_data.items():
            room_id = raw.get("roomId")
            if room_id in rooms_state:
                ghosts[ghost_id] = GhostState(
                    id=ghost_id,
                    room_id=room_id,
                    description=raw.get("description", ""),
                )

        return rooms, rooms_state, items, ghosts

    def _generate_procedural_world(
        self, world_data: Dict[str, object]
    ) -> Tuple[Dict[str, RoomDefinition], Dict[str, RoomState], Dict[str, ItemDefinition], Dict[str, GhostState]]:
        room_count = int(world_data.get("roomCount") or 100)
        if room_count < 1:
            room_count = 1

        rng = random.Random()

        # Degree distribution: ~10% with 1 door, 80% with 2, 10% with 3.
        num_two = int(room_count * 0.8)
        num_one = int(room_count * 0.1)
        if num_one + num_two > room_count:
            num_two = room_count - num_one
        num_three = room_count - num_one - num_two

        degrees: List[int] = [2] * num_two + [1] * num_one + [3] * num_three
        while len(degrees) < room_count:
            degrees.append(2)
        degrees = degrees[: room_count]

        # Ensure sum of degrees is even.
        if sum(degrees) % 2 == 1:
            for i, d in enumerate(degrees):
                if d < 3:
                    degrees[i] = d + 1
                    break

        edges = self._build_random_graph(room_count, degrees, rng)

        # Choose some doors to be locked and assign each a key id.
        locked_doors_target = max(1, room_count // 10)
        all_edges = list(edges)
        if locked_doors_target > len(all_edges):
            locked_doors_target = len(all_edges)
        locked_edges: List[Tuple[int, int]] = rng.sample(all_edges, locked_doors_target)
        locked_edge_keys: Dict[Tuple[int, int], str] = {}
        for idx, edge in enumerate(locked_edges):
            key_id = f"key_{idx}"
            locked_edge_keys[edge] = key_id

        # Assign exits (N/E/S/W) for each edge.
        exits_by_index: List[Dict[str, ExitDefinition]] = [
            {} for _ in range(room_count)
        ]
        used_dirs: List[Set[str]] = [set() for _ in range(room_count)]
        dir_pairs = [
            ("north", "south"),
            ("south", "north"),
            ("east", "west"),
            ("west", "east"),
        ]

        for u, v in edges:
            rng.shuffle(dir_pairs)
            chosen_pair: Optional[Tuple[str, str]] = None
            for d1, d2 in dir_pairs:
                if d1 not in used_dirs[u] and d2 not in used_dirs[v]:
                    chosen_pair = (d1, d2)
                    break
            if chosen_pair is None:
                # Fallback: allow reuse of a direction if necessary.
                d1, d2 = dir_pairs[0]
            else:
                d1, d2 = chosen_pair
            used_dirs[u].add(d1)
            used_dirs[v].add(d2)

            edge_key = (u, v) if (u, v) in locked_edge_keys else (v, u)
            key_id = locked_edge_keys.get(edge_key)
            locked = key_id is not None

            exits_by_index[u][d1] = ExitDefinition(
                direction=d1,
                target_room_id=f"room_{v}",
                locked=locked,
                key_id=key_id,
            )
            exits_by_index[v][d2] = ExitDefinition(
                direction=d2,
                target_room_id=f"room_{u}",
                locked=locked,
                key_id=key_id,
            )

        # Coin distribution: normal between 0 and 10.
        coins_cfg = world_data.get("coins", {})
        mean = float(coins_cfg.get("mean", 4.0))
        std = float(coins_cfg.get("std", 2.0))
        min_coins = int(coins_cfg.get("min", 0))
        max_coins = int(coins_cfg.get("max", 10))

        def sample_coins() -> int:
            value = int(round(rng.gauss(mean, std)))
            if value < min_coins:
                value = min_coins
            if value > max_coins:
                value = max_coins
            return value

        rooms: Dict[str, RoomDefinition] = {}
        rooms_state: Dict[str, RoomState] = {}

        base_appearance = {
            "coinsTemplate": "You see {coinCount} gold coin(s) scattered about.",
            "emptyCoinsTemplate": "You see no coins here.",
            "charactersTemplate": "{names} are here.",
        }

        room_adjectives = [
            "Dusty",
            "Echoing",
            "Shadowed",
            "Dripping",
            "Cracked",
            "Twisting",
            "Silent",
            "Icy",
            "Stifling",
            "Gloomy",
        ]
        room_nouns = [
            "Hall",
            "Cellar",
            "Antechamber",
            "Vault",
            "Passage",
            "Gallery",
            "Crypt",
            "Cavern",
            "Library",
            "Guardroom",
        ]

        for idx in range(room_count):
            room_id = f"room_{idx}"
            adj = room_adjectives[idx % len(room_adjectives)]
            noun = room_nouns[idx % len(room_nouns)]
            name = f"{adj} {noun}"
            description = (
                f"A {adj.lower()} {noun.lower()} carved from damp stone. "
                "Faint echoes hint at unseen passages."
            )
            coins_initial = sample_coins()

            room_def = RoomDefinition(
                id=room_id,
                name=name,
                description=description,
                exits=exits_by_index[idx],
                coins_initial=coins_initial,
                coins_respawn={"enabled": False},
                objects=[],
                appearance=base_appearance,
            )
            rooms[room_id] = room_def
            rooms_state[room_id] = RoomState(
                id=room_id,
                coins=coins_initial,
                objects_state={},
            )

        # Items and keys: roughly one per three rooms.
        items: Dict[str, ItemDefinition] = {}
        ghosts: Dict[str, GhostState] = {}

        total_items = max(1, room_count // 3)
        num_keys = min(len(locked_edge_keys), total_items)
        num_generic = max(0, total_items - num_keys)

        generic_item_descriptions = [
            "a tarnished silver ring",
            "a cracked emerald amulet",
            "a small brass compass",
            "a rune-etched stone",
            "a faded leather bookmark",
            "a glass vial of swirling mist",
            "a chipped obsidian dagger",
            "a delicate bone flute",
            "a copper coin with a square hole",
            "a fragment of a stained map",
            "a smooth stone painted with an eye",
            "a tiny clockwork beetle",
            "a lock of hair tied with red string",
            "a silver bell that makes no sound",
            "a wax-sealed black envelope",
            "a bronze key-shaped brooch",
        ]

        # Create key items for locked doors.
        key_ids: List[str] = []
        for i in range(num_keys):
            key_id = f"key_{i}"
            key_ids.append(key_id)
            items[key_id] = ItemDefinition(
                id=key_id,
                name=f"Strange Key #{i + 1}",
                description="a heavy iron key with jagged teeth",
                is_key=True,
                key_id=key_id,
            )

        # Create generic items.
        for j in range(num_generic):
            item_id = f"item_{j}"
            desc = generic_item_descriptions[
                j % len(generic_item_descriptions)
            ]
            items[item_id] = ItemDefinition(
                id=item_id,
                name=desc,
                description=desc,
                is_key=False,
            )

        # Place items into random rooms.
        room_ids = list(rooms.keys())
        rng.shuffle(room_ids)
        index = 0

        for key_id in key_ids:
            if index >= len(room_ids):
                break
            rid = room_ids[index]
            index += 1
            rooms_state[rid].items.append(key_id)

        for j in range(num_generic):
            if index >= len(room_ids):
                break
            rid = room_ids[index]
            index += 1
            item_id = f"item_{j}"
            rooms_state[rid].items.append(item_id)

        # Ghosts that wander the dungeon.
        ghost_descriptions = [
            "a translucent knight with empty, burning eyes",
            "a tattered-robed specter that drips shadow",
            "a towering phantom crowned in jagged bone",
            "a drifting child-ghost humming a tuneless song",
        ]

        ghost_count = min(3, max(1, room_count // 30))
        for i in range(ghost_count):
            rid = rng.choice(room_ids)
            desc = ghost_descriptions[i % len(ghost_descriptions)]
            ghost_id = f"ghost_{i}"
            ghosts[ghost_id] = GhostState(
                id=ghost_id,
                room_id=rid,
                description=desc,
            )

        return rooms, rooms_state, items, ghosts

    def _write_world_definition(
        self,
        world_name: str,
        rooms: Dict[str, RoomDefinition],
        rooms_state: Dict[str, RoomState],
        items: Dict[str, ItemDefinition],
        ghosts: Dict[str, GhostState],
    ) -> None:
        """Persist the generated world structure to world.json."""
        rooms_out: List[Dict[str, object]] = []
        for room_id, room_def in rooms.items():
            exits: Dict[str, Dict[str, object]] = {}
            for direction, exit_def in room_def.exits.items():
                exits[direction] = {
                    "target": exit_def.target_room_id,
                    "locked": bool(exit_def.locked),
                    "keyId": exit_def.key_id,
                }
            room_items = rooms_state[room_id].items
            rooms_out.append(
                {
                    "id": room_def.id,
                    "name": room_def.name,
                    "description": room_def.description,
                    "exits": exits,
                    "coins": {
                        "initial": room_def.coins_initial,
                        "respawn": room_def.coins_respawn,
                    },
                    "objects": [
                        {
                            "id": obj.id,
                            "name": obj.name,
                            "description": obj.description,
                            "verbs": obj.verbs,
                            "state": obj.state,
                        }
                        for obj in room_def.objects
                    ],
                    "appearance": room_def.appearance,
                    "items": list(room_items),
                }
            )

        items_out: Dict[str, Dict[str, object]] = {}
        for item_id, item in items.items():
            items_out[item_id] = {
                "name": item.name,
                "description": item.description,
                "isKey": bool(item.is_key),
                "keyId": item.key_id,
            }

        ghosts_out: Dict[str, Dict[str, object]] = {}
        for ghost_id, ghost in ghosts.items():
            ghosts_out[ghost_id] = {
                "roomId": ghost.room_id,
                "description": ghost.description,
            }

        data = {
            "worldName": world_name,
            "rooms": rooms_out,
            "items": items_out,
            "ghosts": ghosts_out,
        }

        with open(DATA_DIR / "world.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _build_random_graph(
        self, room_count: int, degrees: List[int], rng: random.Random
    ) -> Set[Tuple[int, int]]:
        if room_count <= 1:
            return set()

        max_attempts = 64
        for _ in range(max_attempts):
            remaining = list(degrees)
            edges: Set[Tuple[int, int]] = set()
            adjacency: List[Set[int]] = [set() for _ in range(room_count)]

            candidates = [i for i, d in enumerate(remaining) if d > 0]
            failed = False

            while candidates:
                u = rng.choice(candidates)
                possible = [
                    v
                    for v in candidates
                    if v != u and v not in adjacency[u]
                ]
                if not possible:
                    failed = True
                    break
                v = rng.choice(possible)
                edge = (u, v) if u < v else (v, u)
                edges.add(edge)
                adjacency[u].add(v)
                adjacency[v].add(u)
                remaining[u] -= 1
                remaining[v] -= 1
                if remaining[u] < 0 or remaining[v] < 0:
                    failed = True
                    break
                candidates = [i for i, d in enumerate(remaining) if d > 0]

            if failed:
                continue
            if any(d != 0 for d in remaining):
                continue
            if self._is_connected(room_count, edges):
                return edges

        # Fallback: simple path if we cannot satisfy the exact degree distribution.
        fallback_edges: Set[Tuple[int, int]] = set()
        for i in range(room_count - 1):
            fallback_edges.add((i, i + 1))
        return fallback_edges

    def _is_connected(self, room_count: int, edges: Set[Tuple[int, int]]) -> bool:
        if room_count == 0:
            return True
        adjacency: Dict[int, Set[int]] = {i: set() for i in range(room_count)}
        for u, v in edges:
            adjacency[u].add(v)
            adjacency[v].add(u)
        visited: Set[int] = set()
        stack: List[int] = [0]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            stack.extend(adjacency[node] - visited)
        return len(visited) == room_count

    async def allocate_player(self, character_id: str) -> PlayerState:
        async with self.lock:
            if character_id in self.state.active_characters:
                raise ValueError("Character already in use")
            character = self.state.config.characters[character_id]
            starting_room = character.starting_room
            if starting_room not in self.state.rooms_state:
                starting_room = next(iter(self.state.rooms_state.keys()))

            saved = self.state.character_saves.get(character_id)
            if saved:
                room_id = (
                    saved.room_id
                    if saved.room_id in self.state.rooms_state
                    else starting_room
                )
                coins = saved.coins
                items = [
                    item_id
                    for item_id in saved.items
                    if item_id in self.state.config.items
                ]
            else:
                room_id = starting_room
                coins = 0
                items = []

            player_id = str(uuid.uuid4())
            player = PlayerState(
                player_id=player_id,
                character_id=character.id,
                name=character.name,
                room_id=room_id,
                coins=coins,
                items=items,
            )
            self.state.players[player_id] = player
            self.state.active_characters.add(character.id)
            room_state = self.state.rooms_state[player.room_id]
            room_state.players.add(player_id)
            self._update_character_save_unlocked(player)
            self._save_state_unlocked()
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
            # Character_saves is intentionally preserved so that player
            # state can be restored on next login.
            self._save_state_unlocked()

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

    async def move_player(
        self, player_id: str, direction: str
    ) -> Dict[str, object]:
        async with self.lock:
            player = self.state.players[player_id]
            room_def = self.state.config.rooms[player.room_id]
            dir_key = direction.lower()
            exit_def = room_def.exits.get(dir_key)
            if not exit_def:
                raise ValueError("You cannot go that way.")
            target_room_id = exit_def.target_room_id

            if exit_def.locked:
                # Check if the player has a matching key.
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
                # Unlock this door and its counterpart.
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
            self._save_state_unlocked()
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
            self._save_state_unlocked()
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

            taken_names = []
            for item_id in taken_ids:
                item = self.state.config.items.get(item_id)
                if item:
                    taken_names.append(item.name)

            self._update_character_save_unlocked(player)
            self._save_state_unlocked()

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
        """Return a 15x15 ASCII minimap around the given player.

        Only the current room and its immediate N/S/E/W neighbours are shown.

        Rooms are 2x2 blocks:
        - '*' for the player's room
        - 'P' for rooms containing other players
        - '.' for discovered empty rooms
        Exits are shown as '-' and '|' between blocks and always correspond
        exactly to available movement commands from the current room.
        """
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
        step = 4  # distance between room centres

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

        # Draw the current room at the centre.
        draw_room_block(center_x, center_y, has_self=True, has_other=has_other)

        # Draw immediate neighbours and direct connections from the current room.
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

            # Draw the corridor between the current room and the neighbour.
            if dx == 0:
                # vertical connection
                link_x = center_x
                link_y = center_y + (dy * (step // 2))
                if 0 <= link_x < width and 0 <= link_y < height:
                    grid[link_y][link_x] = "|"
            else:
                # horizontal connection
                link_x = center_x + (dx * (step // 2))
                link_y = center_y
                if 0 <= link_x < width and 0 <= link_y < height:
                    grid[link_y][link_x] = "-"

        return "\n".join("".join(row) for row in grid)

    async def move_ghosts_and_collect_events(self) -> Dict[str, List[str]]:
        """Move ghosts randomly and return messages for players who see them."""
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

            # After moving, notify any players who share a room with a ghost.
            for ghost in self.state.ghosts.values():
                for player in self.state.players.values():
                    if player.room_id == ghost.room_id:
                        msg = (
                            f"A ghost passes through the room: {ghost.description}."
                        )
                        events.setdefault(player.player_id, []).append(msg)
            return events
