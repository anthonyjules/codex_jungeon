from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..models import (
    CharacterTemplate,
    ExitDefinition,
    GhostState,
    ItemDefinition,
    RoomDefinition,
    RoomObject,
    RoomState,
    WorldConfig,
)


class WorldLoader:
    """Load world configuration and initial runtime state from disk."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def load(self) -> Tuple[WorldConfig, Dict[str, RoomState], Dict[str, GhostState]]:
        with open(self.data_dir / "world.json", "r", encoding="utf-8") as f:
            world_data = json.load(f)
        with open(self.data_dir / "characters.json", "r", encoding="utf-8") as f:
            chars_data = json.load(f)
        with open(self.data_dir / "verbs.json", "r", encoding="utf-8") as f:
            verbs_data = json.load(f)

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

        return config, rooms_state, ghosts

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
            room_items = [item_id for item_id in r.get("items", []) if item_id in items]
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
    ) -> Tuple[
        Dict[str, RoomDefinition],
        Dict[str, RoomState],
        Dict[str, ItemDefinition],
        Dict[str, GhostState],
    ]:
        room_count = int(world_data.get("roomCount") or 100)
        if room_count < 1:
            room_count = 1

        rng = random.Random()

        num_two = int(room_count * 0.8)
        num_one = int(room_count * 0.1)
        if num_one + num_two > room_count:
            num_two = room_count - num_one
        num_three = room_count - num_one - num_two

        degrees: List[int] = [2] * num_two + [1] * num_one + [3] * num_three
        while len(degrees) < room_count:
            degrees.append(2)
        degrees = degrees[:room_count]

        if sum(degrees) % 2 == 1:
            for i, d in enumerate(degrees):
                if d < 3:
                    degrees[i] = d + 1
                    break

        edges = self._build_random_graph(room_count, degrees, rng)

        locked_doors_target = max(1, room_count // 10)
        all_edges = list(edges)
        if locked_doors_target > len(all_edges):
            locked_doors_target = len(all_edges)
        locked_edges: List[Tuple[int, int]] = rng.sample(all_edges, locked_doors_target)
        locked_edge_keys: Dict[Tuple[int, int], str] = {}
        for idx, edge in enumerate(locked_edges):
            key_id = f"key_{idx}"
            locked_edge_keys[edge] = key_id

        exits_by_index: List[Dict[str, ExitDefinition]] = [{} for _ in range(room_count)]
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

        for j in range(num_generic):
            item_id = f"item_{j}"
            desc = generic_item_descriptions[j % len(generic_item_descriptions)]
            items[item_id] = ItemDefinition(
                id=item_id,
                name=desc,
                description=desc,
                is_key=False,
            )

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
        rooms_out: List[Dict[str, object]] = []
        for room_id, room_def in rooms.items():
            state = rooms_state[room_id]
            rooms_out.append(
                {
                    "id": room_id,
                    "name": room_def.name,
                    "description": room_def.description,
                    "exits": {
                        direction: self._exit_to_dict(exit_def)
                        for direction, exit_def in room_def.exits.items()
                    },
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
                    "items": list(state.items),
                }
            )

        ghosts_out = {
            ghost_id: {"roomId": ghost.room_id, "description": ghost.description}
            for ghost_id, ghost in ghosts.items()
        }

        items_out = {
            item_id: {
                "name": item.name,
                "description": item.description,
                "isKey": item.is_key,
                "keyId": item.key_id,
            }
            for item_id, item in items.items()
        }

        world_json = {
            "worldName": world_name,
            "rooms": rooms_out,
            "items": items_out,
            "ghosts": ghosts_out,
        }

        with open(self.data_dir / "world.generated.json", "w", encoding="utf-8") as f:
            json.dump(world_json, f, indent=2)

    def _exit_to_dict(self, exit_def: ExitDefinition) -> Dict[str, object]:
        return {
            "target": exit_def.target_room_id,
            "locked": exit_def.locked,
            "keyId": exit_def.key_id,
        }

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
                possible = [v for v in candidates if v != u and v not in adjacency[u]]
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
