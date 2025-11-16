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
class ItemDefinition:
    id: str
    name: str
    description: str
    is_key: bool = False
    key_id: Optional[str] = None


@dataclass
class ExitDefinition:
    direction: str
    target_room_id: str
    locked: bool = False
    key_id: Optional[str] = None


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
    exits: Dict[str, ExitDefinition]
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
    items: List[str] = field(default_factory=list)


@dataclass
class PlayerState:
    player_id: str
    character_id: str
    name: str
    room_id: str
    coins: int = 0
    items: List[str] = field(default_factory=list)


@dataclass
class GhostState:
    id: str
    room_id: str
    description: str


@dataclass
class CharacterSave:
    character_id: str
    room_id: str
    coins: int
    items: List[str]


@dataclass
class WorldConfig:
    rooms: Dict[str, RoomDefinition]
    characters: Dict[str, CharacterTemplate]
    items: Dict[str, ItemDefinition]
    emotes: Dict[str, str]
    allowed_object_verbs: List[str]


@dataclass
class WorldState:
    config: WorldConfig
    rooms_state: Dict[str, RoomState]
    players: Dict[str, PlayerState] = field(default_factory=dict)
    active_characters: Set[str] = field(default_factory=set)
    ghosts: Dict[str, GhostState] = field(default_factory=dict)
    character_saves: Dict[str, CharacterSave] = field(default_factory=dict)


def compose_room_description(
    room_def: RoomDefinition,
    room_state: RoomState,
    player_states: List[PlayerState],
    config: WorldConfig,
) -> str:
    """Build the description text for a room, including coins, items, and characters."""
    lines: List[str] = [room_def.description]

    if room_state.coins > 0:
        template = room_def.appearance.get("coinsTemplate") or ""
        if template:
            lines.append(template.format(coinCount=room_state.coins))
    else:
        template = room_def.appearance.get("emptyCoinsTemplate") or ""
        if template:
            lines.append(template)

    if room_state.items:
        item_names: List[str] = []
        for item_id in room_state.items:
            item = config.items.get(item_id)
            if item:
                item_names.append(item.name)
        if item_names:
            lines.append("Items here: " + ", ".join(item_names) + ".")

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
