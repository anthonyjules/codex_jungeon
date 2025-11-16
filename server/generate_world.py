from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List, Set, Tuple

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WORLD_FILE = DATA_DIR / "world.json"
SAVE_FILE = DATA_DIR / "savegame.json"


def _build_random_graph(
    room_count: int, degrees: List[int], rng: random.Random
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
        if _is_connected(room_count, edges):
            return edges

    # Fallback: simple path if we cannot satisfy the exact degree distribution.
    fallback_edges: Set[Tuple[int, int]] = set()
    for i in range(room_count - 1):
        fallback_edges.add((i, i + 1))
    return fallback_edges


def _is_connected(room_count: int, edges: Set[Tuple[int, int]]) -> bool:
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


def generate_world_definition(
    room_count: int,
    coins_mean: float = 4.0,
    coins_std: float = 2.0,
    coins_min: int = 0,
    coins_max: int = 10,
) -> Dict[str, object]:
    """Generate a complete world definition as a JSON-serialisable dict."""
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

    if sum(degrees) % 2 == 1:
        for i, d in enumerate(degrees):
            if d < 3:
                degrees[i] = d + 1
                break

    edges = _build_random_graph(room_count, degrees, rng)

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
    exits_by_index: List[Dict[str, Dict[str, object]]] = [
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
        chosen_pair: Tuple[str, str] | None = None
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

        exits_by_index[u][d1] = {
            "target": f"room_{v}",
            "locked": locked,
            "keyId": key_id,
        }
        exits_by_index[v][d2] = {
            "target": f"room_{u}",
            "locked": locked,
            "keyId": key_id,
        }

    def sample_coins() -> int:
        value = int(round(rng.gauss(coins_mean, coins_std)))
        if value < coins_min:
            value = coins_min
        if value > coins_max:
            value = coins_max
        return value

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

    rooms: List[Dict[str, object]] = []
    room_ids: List[str] = []
    for idx in range(room_count):
        room_id = f"room_{idx}"
        room_ids.append(room_id)
        adj = room_adjectives[idx % len(room_adjectives)]
        noun = room_nouns[idx % len(room_nouns)]
        name = f"{adj} {noun}"
        description = (
            f"A {adj.lower()} {noun.lower()} carved from damp stone. "
            "Faint echoes hint at unseen passages."
        )
        coins_initial = sample_coins()
        appearance = {
            "coinsTemplate": "You see {coinCount} gold coin(s) scattered about.",
            "emptyCoinsTemplate": "You see no coins here.",
            "charactersTemplate": "{names} are here.",
        }
        rooms.append(
            {
                "id": room_id,
                "name": name,
                "description": description,
                "exits": exits_by_index[idx],
                "coins": {
                    "initial": coins_initial,
                    "respawn": {"enabled": False},
                },
                "objects": [],
                "appearance": appearance,
                "items": [],
            }
        )

    room_index_by_id = {r["id"]: i for i, r in enumerate(rooms)}

    # Items and keys.
    items: Dict[str, Dict[str, object]] = {}

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
        items[key_id] = {
            "name": f"Strange Key #{i + 1}",
            "description": "a heavy iron key with jagged teeth",
            "isKey": True,
            "keyId": key_id,
        }

    for j in range(num_generic):
        item_id = f"item_{j}"
        desc = generic_item_descriptions[j % len(generic_item_descriptions)]
        items[item_id] = {
            "name": desc,
            "description": desc,
            "isKey": False,
            "keyId": None,
        }

    rng.shuffle(room_ids)
    index = 0

    for key_id in key_ids:
        if index >= len(room_ids):
            break
        rid = room_ids[index]
        index += 1
        ri = room_index_by_id[rid]
        rooms[ri]["items"].append(key_id)

    for j in range(num_generic):
        if index >= len(room_ids):
            break
        rid = room_ids[index]
        index += 1
        item_id = f"item_{j}"
        ri = room_index_by_id[rid]
        rooms[ri]["items"].append(item_id)

    ghost_descriptions = [
        "a translucent knight with empty, burning eyes",
        "a tattered-robed specter that drips shadow",
        "a towering phantom crowned in jagged bone",
        "a drifting child-ghost humming a tuneless song",
    ]

    ghosts: Dict[str, Dict[str, object]] = {}
    ghost_count = min(3, max(1, room_count // 30))
    for i in range(ghost_count):
        rid = rng.choice(room_ids)
        desc = ghost_descriptions[i % len(ghost_descriptions)]
        ghost_id = f"ghost_{i}"
        ghosts[ghost_id] = {"roomId": rid, "description": desc}

    return {
        "worldName": "The Jungeon",
        "rooms": rooms,
        "items": items,
        "ghosts": ghosts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a new Jungeon world map.")
    parser.add_argument(
        "--room-count",
        type=int,
        default=100,
        help="Number of rooms to generate (default: 100)",
    )
    args = parser.parse_args()

    world_def = generate_world_definition(args.room_count)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(WORLD_FILE, "w", encoding="utf-8") as f:
        json.dump(world_def, f, indent=2)

    # Reset dynamic state whenever a new world is generated.
    if SAVE_FILE.exists():
        SAVE_FILE.unlink()

    print(f"Generated world with {args.room_count} rooms at {WORLD_FILE}")


if __name__ == "__main__":
    main()

