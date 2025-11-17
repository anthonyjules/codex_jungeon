from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

from ..schemas import ServerMessage
from ..services.connection_manager import BroadcastEvent, ConnectionManager
from ..world.engine import WorldEngine


@dataclass(frozen=True)
class CommandInput:
    action: str
    args: List[str] = field(default_factory=list)
    verb: Optional[str] = None


@dataclass
class CommandResult:
    replies: List[ServerMessage] = field(default_factory=list)
    broadcasts: List[BroadcastEvent] = field(default_factory=list)
    refresh_room: bool = False
    refresh_inventory: bool = False


class CommandHandler(Protocol):
    async def __call__(
        self,
        world: WorldEngine,
        connections: ConnectionManager,
        player_id: str,
        command: CommandInput,
    ) -> CommandResult: ...
