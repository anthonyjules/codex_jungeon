from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class CharacterTemplate:
    id: str
    name: str
    short_description: str
    long_description: str
    starting_room: str
    appearance_in_room: str


@dataclass
class RoomObject:
    id: str
    name: str
    description: str
    verbs: List[str]
    state: str = "idle"


@dataclass
class RoomDefinition:
    id: str
    name: str
    description: str
    exits: Dict[str, str]
    coins_initial: int
    coins_respawn: Dict[str, object]
    objects: List[RoomObject]
    appearance: Dict[str, str]


@dataclass
class RoomState:
    id: str
    coins: int
    players: Set[str] = field(default_factory=set)
    objects_state: Dict[str, str] = field(default_factory=dict)


@dataclass
class PlayerState:
    player_id: str
    character_id: str
    name: str
    room_id: str
    coins: int = 0


@dataclass
class WorldConfig:
    rooms: Dict[str, RoomDefinition]
    characters: Dict[str, CharacterTemplate]
    emotes: Dict[str, str]
    allowed_object_verbs: List[str]


@dataclass
class WorldState:
    config: WorldConfig
    rooms_state: Dict[str, RoomState]
    players: Dict[str, PlayerState] = field(default_factory=dict)
    active_characters: Set[str] = field(default_factory=set)


def compose_room_description(
    room_def: RoomDefinition,
    room_state: RoomState,
    player_states: List[PlayerState],
    config: WorldConfig,
) -> str:
    """Build the description text for a room, including coins and characters."""
    lines: List[str] = [room_def.description]

    if room_state.coins > 0:
        template = room_def.appearance.get("coinsTemplate") or ""
        if template:
            lines.append(template.format(coinCount=room_state.coins))
    else:
        template = room_def.appearance.get("emptyCoinsTemplate") or ""
        if template:
            lines.append(template)

    if player_states:
        template = room_def.appearance.get("charactersTemplate") or "{names} are here."
        appearances: List[str] = []
        for p in player_states:
            character = config.characters.get(p.character_id)
            if character:
                appearances.append(
                    character.appearance_in_room.format(name=character.name)
                )
            else:
                appearances.append(f"{p.name} is here.")
        if appearances:
            lines.append(template.format(names=" ".join(appearances)))

    return "\n".join(lines)

