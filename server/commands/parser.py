from __future__ import annotations

from typing import List

from .base import CommandInput


def parse_command_input(text: str) -> CommandInput:
    cleaned = (text or "").strip()
    if not cleaned:
        return CommandInput(action="noop")
    if cleaned.startswith("/"):
        # Check for special messaging commands first
        parts = cleaned[1:].strip().split(None, 1)  # Split on first space only
        if not parts:
            return CommandInput(action="emote", verb="")
        verb = parts[0].lower()
        remaining = parts[1] if len(parts) > 1 else ""

        if verb == "tell":
            # /tell {character} {message} or /tell all {message}
            if remaining:
                remaining_parts = remaining.split(None, 1)
                target = remaining_parts[0] if remaining_parts else ""
                message = remaining_parts[1] if len(remaining_parts) > 1 else ""
                return CommandInput(action="tell", args=[target, message] if message else [target])
            return CommandInput(action="tell", args=[])
        elif verb == "yell":
            # /yell {character} {message}
            if remaining:
                remaining_parts = remaining.split(None, 1)
                target = remaining_parts[0] if remaining_parts else ""
                message = remaining_parts[1] if len(remaining_parts) > 1 else ""
                return CommandInput(action="yell", args=[target, message] if message else [target])
            return CommandInput(action="yell", args=[])
        elif verb == "reply":
            # /reply {message}
            return CommandInput(action="reply", args=[remaining] if remaining else [])
        else:
            # Fall back to emote
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
