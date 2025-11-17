from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from ..models import CharacterSave, WorldState


class WorldRepository:
    """Persist and restore dynamic world state."""

    def __init__(self, save_file: Path) -> None:
        self.save_file = save_file

    def restore_state(self, state: WorldState) -> None:
        """Populate runtime state with data from disk if available."""
        if not self.save_file.exists():
            return
        try:
            with open(self.save_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        rooms_data: Dict[str, Dict[str, object]] = data.get("rooms", {})
        for room_id, raw in rooms_data.items():
            room_state = state.rooms_state.get(room_id)
            if not room_state:
                continue
            coins = raw.get("coins")
            if isinstance(coins, int):
                room_state.coins = coins
            items = raw.get("items", [])
            if isinstance(items, list):
                room_state.items = [
                    item_id for item_id in items if item_id in state.config.items
                ]

        characters_data = data.get("characters", {})
        for char_id, raw in characters_data.items():
            room_id = raw.get("roomId")
            if room_id not in state.rooms_state:
                room_id = next(iter(state.rooms_state.keys()))
            coins = int(raw.get("coins", 0))
            items = [
                item_id
                for item_id in raw.get("items", [])
                if item_id in state.config.items
            ]
            state.character_saves[char_id] = CharacterSave(
                character_id=char_id,
                room_id=room_id,
                coins=coins,
                items=items,
            )

        ghosts_data = data.get("ghosts", {})
        for ghost_id, raw in ghosts_data.items():
            ghost_state = state.ghosts.get(ghost_id)
            if not ghost_state:
                continue
            room_id = raw.get("roomId")
            if room_id in state.rooms_state:
                ghost_state.room_id = room_id

    def build_save_payload(self, state: WorldState) -> Dict[str, object]:
        return {
            "rooms": {
                room_id: {
                    "coins": room_state.coins,
                    "items": list(room_state.items),
                }
                for room_id, room_state in state.rooms_state.items()
            },
            "characters": {
                char_id: {
                    "roomId": cs.room_id,
                    "coins": cs.coins,
                    "items": list(cs.items),
                }
                for char_id, cs in state.character_saves.items()
            },
            "ghosts": {
                ghost_id: {"roomId": ghost.room_id}
                for ghost_id, ghost in state.ghosts.items()
            },
        }

    def write_save(self, payload: Dict[str, object]) -> None:
        try:
            with open(self.save_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            # Persistence errors should not break gameplay.
            return
