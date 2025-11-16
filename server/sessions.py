from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Session:
    session_id: str
    player_id: str


class SessionManager:
    def __init__(self) -> None:
        self._by_session: Dict[str, Session] = {}

    def create_session(self, session_id: str, player_id: str) -> Session:
        session = Session(session_id=session_id, player_id=player_id)
        self._by_session[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._by_session.get(session_id)

    def remove_session(self, session_id: str) -> None:
        self._by_session.pop(session_id, None)

