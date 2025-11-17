from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CharacterInfo(BaseModel):
    id: str
    name: str
    shortDescription: str


class AvailableCharactersResponse(BaseModel):
    characters: List[CharacterInfo]


class LoginRequest(BaseModel):
    characterId: str


class LoginResponse(BaseModel):
    sessionId: str
    playerName: str
    characterId: str


class CommandMessage(BaseModel):
    type: str
    input: Optional[str] = None


class ServerMessage(BaseModel):
    type: str
    data: Dict[str, Any]


class DebugSnapshot(BaseModel):
    roomState: Dict[str, Any]
    inventory: Dict[str, Any]
