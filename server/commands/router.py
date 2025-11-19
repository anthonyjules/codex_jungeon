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
            "tell": tell_handler,
            "yell": yell_handler,
            "reply": reply_handler,
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


async def tell_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    """Handle /tell {character} {message} or /tell all {message}"""
    args = command.args or []
    if len(args) < 2:
        raise ValueError("Usage: /tell {character} {message} or /tell all {message}")

    target = args[0].strip().lower() if args[0] else ""
    message = " ".join(args[1:])

    if not message:
        raise ValueError("What do you want to tell them?")

    sender = await world.get_player(player_id)
    if not sender:
        raise ValueError("You are not a valid player.")

    sender_name = sender.name
    replies: List[ServerMessage] = []

    # Check for "all" target first (before trying to resolve as character name)
    # Normalize target to handle any edge cases
    target_normalized = target.strip().lower()
    if target_normalized == "all":
        # Send to all online players
        player_ids = connections.get_all_connected_player_ids()
        message_text = f"{sender_name} tells everyone: '{message}'"
        payload = ServerMessage(type="event", data={"text": message_text}).model_dump()

        # Update last_message_sender_id for all recipients (so they can /reply)
        async with world.lock:
            for recipient_id in player_ids:
                if recipient_id != player_id:  # Don't update sender's own last_message_sender_id
                    recipient_player = world.state.players.get(recipient_id)
                    if recipient_player:
                        recipient_player.last_message_sender_id = player_id

        # Send to all players including sender
        await connections.send_to_all(payload)
        return CommandResult()
    else:
        # Send to specific character
        # Use the normalized target for character resolution
        target_player_id = await world.resolve_character_name(target_normalized, connections)
        if not target_player_id:
            raise ValueError(f"'{target}' is not online or the name is ambiguous.")

        if target_player_id == player_id:
            raise ValueError("You cannot tell yourself.")

        target_player = await world.get_player(target_player_id)
        if not target_player:
            raise ValueError(f"'{target}' is not online.")

        # Update target's last_message_sender_id
        async with world.lock:
            # Get player again to ensure we're modifying the state object
            state_player = world.state.players.get(target_player_id)
            if state_player:
                state_player.last_message_sender_id = player_id

        # Send message to target
        target_message = f"{sender_name} tells you: '{message}'"
        await connections.send(
            target_player_id,
            ServerMessage(type="event", data={"text": target_message}).model_dump()
        )

        # Send confirmation to sender
        sender_message = f"You tell {target_player.name}: '{message}'"
        replies.append(ServerMessage(type="event", data={"text": sender_message}))

        return CommandResult(replies=replies)


async def yell_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    """Handle /yell {character} {message} or /yell all {message}"""
    args = command.args or []
    if len(args) < 2:
        raise ValueError("Usage: /yell {character} {message} or /yell all {message}")

    target = args[0].strip().lower() if args[0] else ""
    message = " ".join(args[1:])

    if not message:
        raise ValueError("What do you want to yell?")

    sender = await world.get_player(player_id)
    if not sender:
        raise ValueError("You are not a valid player.")

    sender_name = sender.name.upper()
    message_upper = message.upper()
    replies: List[ServerMessage] = []

    # Check for "all" target first (before trying to resolve as character name)
    target_normalized = target.strip().lower()
    if target_normalized == "all":
        # Send to all online players
        player_ids = connections.get_all_connected_player_ids()
        message_text = f"{sender_name} YELLS AT EVERYONE: '{message_upper}'"
        payload = ServerMessage(type="event", data={"text": message_text}).model_dump()

        # Update last_message_sender_id for all recipients (so they can /reply)
        async with world.lock:
            for recipient_id in player_ids:
                if recipient_id != player_id:  # Don't update sender's own last_message_sender_id
                    recipient_player = world.state.players.get(recipient_id)
                    if recipient_player:
                        recipient_player.last_message_sender_id = player_id

        # Send to all players including sender
        await connections.send_to_all(payload)
        return CommandResult()

    # Send to specific character
    target_player_id = await world.resolve_character_name(target_normalized, connections)
    if not target_player_id:
        raise ValueError(f"'{target}' is not online or the name is ambiguous.")

    if target_player_id == player_id:
        raise ValueError("You cannot yell at yourself.")

    target_player = await world.get_player(target_player_id)
    if not target_player:
        raise ValueError(f"'{target}' is not online.")

    # Update target's last_message_sender_id
    async with world.lock:
        # Get player again to ensure we're modifying the state object
        state_player = world.state.players.get(target_player_id)
        if state_player:
            state_player.last_message_sender_id = player_id

    # Send message to target (ALL CAPS)
    target_message = f"{sender_name} YELLS AT YOU: '{message_upper}'"
    await connections.send(
        target_player_id,
        ServerMessage(type="event", data={"text": target_message}).model_dump()
    )

    # Send confirmation to sender
    sender_message = f"You yell at {target_player.name}: '{message_upper}'"
    replies.append(ServerMessage(type="event", data={"text": sender_message}))

    return CommandResult(replies=replies)


async def reply_handler(
    world: WorldEngine,
    connections: ConnectionManager,
    player_id: str,
    command: CommandInput,
) -> CommandResult:
    """Handle /reply {message}"""
    args = command.args or []
    if not args:
        raise ValueError("Usage: /reply {message}")

    message = " ".join(args)

    sender = await world.get_player(player_id)
    if not sender:
        raise ValueError("You are not a valid player.")

    # Get the last person who sent a message
    last_sender_id = sender.last_message_sender_id
    if not last_sender_id:
        raise ValueError("You have no one to reply to.")

    last_sender = await world.get_player(last_sender_id)
    if not last_sender:
        raise ValueError("The person you're replying to is no longer online.")

    # Check if last sender is still online
    if not connections.get(last_sender_id):
        raise ValueError("The person you're replying to is no longer online.")

    # Use tell_handler logic
    sender_name = sender.name

    # Update last sender's last_message_sender_id
    async with world.lock:
        # Get player again to ensure we're modifying the state object
        state_sender = world.state.players.get(last_sender_id)
        if state_sender:
            state_sender.last_message_sender_id = player_id

    # Send message to last sender
    target_message = f"{sender_name} tells you: '{message}'"
    await connections.send(
        last_sender_id,
        ServerMessage(type="event", data={"text": target_message}).model_dump()
    )

    # Send confirmation to sender
    sender_message = f"You tell {last_sender.name}: '{message}'"
    return CommandResult(
        replies=[ServerMessage(type="event", data={"text": sender_message})]
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
