from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import (
    AvailableCharactersResponse,
    CharacterInfo,
    DebugSnapshot,
    LoginRequest,
    LoginResponse,
)
from ..services.game_service import GameService


def create_http_router(game: GameService) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/api/characters/available", response_model=AvailableCharactersResponse
    )
    async def get_available_characters() -> AvailableCharactersResponse:
        characters = await game.list_available_characters()
        return AvailableCharactersResponse(
            characters=[
                CharacterInfo(
                    id=c.id,
                    name=c.name,
                    shortDescription=c.short_description,
                )
                for c in characters
            ]
        )

    @router.post("/api/login", response_model=LoginResponse)
    async def login(req: LoginRequest) -> LoginResponse:
        session_id, player = await game.login(req.characterId)
        return LoginResponse(
            sessionId=session_id,
            playerName=player.name,
            characterId=player.character_id,
        )

    @router.get("/api/debug/session/{session_id}", response_model=DebugSnapshot)
    async def debug_session(session_id: str) -> DebugSnapshot:
        session = game.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        room_state = await game.describe_room(session.player_id)
        inventory = await game.get_inventory(session.player_id)
        return DebugSnapshot(roomState=room_state, inventory=inventory)

    return router
