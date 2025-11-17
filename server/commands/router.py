from __future__ import annotations

import re
from typing import Awaitable, Callable, Dict, List, Optional

from ..schemas import ServerMessage
from ..services.connection_manager import BroadcastEvent, ConnectionManager
from ..world.engine import WorldEngine
from .base import CommandHandler, CommandInput, CommandResult


class CommandRouter:
    """Map parsed commands to handler callables."""

    def __init__(self, world: WorldEngine, connections: ConnectionManager) -> None:
        self.world = world
        self.connections = connections
        self._handlers: Dict[str, CommandHandler] = {
            "noop": noop_handler,
            "go": go_handler,
            "collect": collect_handler,
            "drop": drop_handler,
            "take": take_handler,
            "look": look_handler,
            "emote": emote_handler,
            "say": say_handler,
        }

    async def dispatch(
        self,
        player_id: str,
        command: CommandInput,
    ) -> CommandResult:
        handler = self._handlers.get(command.action)
        if not handler:
            return CommandResult(
                replies=[
                    ServerMessage(
                        type="error",
                        data={"message": f"Unknown command: {command.action}"},
                    )
                ]
            )
        return await handler(self.world, self.connections, player_id, command)


async def noop_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    return CommandResult()


async def go_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    args = command.args or []
    if not args:
        raise ValueError("Specify a direction (north/south/east/west).")
    direction = args[0]
    room_info = await world.move_player(player_id, direction)
    return CommandResult(
        replies=[ServerMessage(type="roomState", data=room_info)],
        broadcasts=[
            BroadcastEvent(
                player_id=player_id,
                text="You hear footsteps as someone moves.",
                include_self=False,
            )
        ],
    )


async def collect_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    info = await world.collect_coins(player_id)
    return CommandResult(
        replies=[
            ServerMessage(
                type="event",
                data={"text": f"You collect {info['collected']} coin(s)."},
            )
        ],
        broadcasts=[
            BroadcastEvent(
                player_id=player_id,
                text="Someone collects coins nearby.",
                include_self=False,
            )
        ],
        refresh_room=True,
        refresh_inventory=True,
    )


async def drop_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    info = await world.drop_coins(player_id)
    return CommandResult(
        replies=[
            ServerMessage(
                type="event",
                data={"text": f"You drop {info['dropped']} coin(s)."},
            )
        ],
        broadcasts=[
            BroadcastEvent(
                player_id=player_id,
                text="You hear coins clatter onto the floor.",
                include_self=False,
            )
        ],
        refresh_room=True,
        refresh_inventory=True,
    )


async def take_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    query = " ".join(command.args) if command.args else None
    info = await world.take_items(player_id, query)
    replies: List[ServerMessage] = []
    broadcasts: List[BroadcastEvent] = []
    taken = info.get("taken") or []
    if taken:
        taken_text = ", ".join(taken)
        replies.append(
            ServerMessage(
                type="event",
                data={"text": f"You take {taken_text}."},
            )
        )
        broadcasts.append(
            BroadcastEvent(
                player_id=player_id,
                text="Someone picks something up nearby.",
                include_self=False,
            )
        )
    return CommandResult(
        replies=replies,
        broadcasts=broadcasts,
        refresh_inventory=True,
    )


async def look_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    return CommandResult(refresh_room=True)


async def emote_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    verb = command.verb
    if not verb:
        raise ValueError("Specify an emote, e.g. /sneeze.")
    emote_text = await world.get_emote_message(player_id, verb)
    if not emote_text:
        raise ValueError("Unknown emote.")
    player = await world.get_player(player_id)
    reply_text = _format_self_emote(emote_text, player.name if player else None)
    return CommandResult(
        replies=[
            ServerMessage(
                type="event",
                data={"text": reply_text},
            )
        ],
        broadcasts=[
            BroadcastEvent(
                player_id=player_id,
                text=emote_text,
                include_self=False,
            )
        ],
    )


async def say_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    args = command.args or []
    if not args:
        raise ValueError("Say what?")
    text = " ".join(args)
    player = await world.get_player(player_id)
    speaker_name = player.name if player else "Someone"
    return CommandResult(
        replies=[
            ServerMessage(
                type="event",
                data={"text": f'You say: "{text}"'},
            )
        ],
        broadcasts=[
            BroadcastEvent(
                player_id=player_id,
                text=f'{speaker_name} says: "{text}"',
                include_self=False,
            )
        ],
    )


_WORD_PATTERN = re.compile(r"([A-Za-z']+)(.*)")


def _format_self_emote(emote_text: str, player_name: Optional[str]) -> str:
    """Convert the broadcast emote into a second-person message for the player."""
    template = emote_text
    if player_name:
        prefix = f"{player_name} "
        if template.startswith(prefix):
            template = template[len(prefix) :]
    template = template.lstrip()
    match = _WORD_PATTERN.match(template)
    if not match:
        return f"You {template}".strip()
    verb, remainder = match.groups()
    verb = _verb_to_second_person(verb)
    return f"You {verb}{remainder}"


def _verb_to_second_person(verb: str) -> str:
    lower = verb.lower()
    if lower.endswith("ies") and len(verb) > 3:
        base = verb[:-3] + "y"
    elif lower.endswith("ezes"):
        base = verb[:-1]
    elif lower.endswith(("ses", "xes", "zes", "ches", "shes", "oes")):
        base = verb[:-2]
    elif lower.endswith("s") and not lower.endswith("ss"):
        base = verb[:-1]
    else:
        base = verb

    if verb.isupper():
        return base.upper()
    if verb.istitle():
        return base.capitalize()
    return base
