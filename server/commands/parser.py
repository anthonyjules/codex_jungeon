from __future__ import annotations

from typing import List

from .base import CommandInput


def parse_command_input(text: str) -> CommandInput:
    cleaned = (text or "").strip()
    if not cleaned:
        return CommandInput(action="noop")
    if cleaned.startswith("/"):
        verb = cleaned[1:].strip().lower()
        return CommandInput(action="emote", verb=verb)
    parts: List[str] = cleaned.split()
    if not parts:
        return CommandInput(action="noop")
    verb = parts[0].lower()
    args = parts[1:]

    direction_aliases = {"n": "north", "s": "south", "e": "east", "w": "west"}
    if verb in direction_aliases and not args:
        return CommandInput(action="go", args=[direction_aliases[verb]])
    if verb in {"north", "south", "east", "west"} and not args:
        return CommandInput(action="go", args=[verb])

    return CommandInput(action=verb, args=args)
