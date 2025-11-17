from __future__ import annotations

import asyncio
from typing import Dict, Optional

from ..world.repository import WorldRepository


class PersistenceWorker:
    """Background task that writes save payloads without blocking the game loop."""

    def __init__(self, repository: WorldRepository) -> None:
        self.repository = repository
        self._queue: asyncio.Queue[Dict[str, object]] = asyncio.Queue()
        self._task: Optional[asyncio.Task[None]] = None

    def schedule_save(self, payload: Dict[str, object]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Called outside the event loop (e.g., during startup); write synchronously.
            self.repository.write_save(payload)
            return

        self._queue.put_nowait(payload)
        if not self._task or self._task.done():
            self._task = loop.create_task(self._drain_queue())

    async def _drain_queue(self) -> None:
        while not self._queue.empty():
            payload = await self._queue.get()
            try:
                await asyncio.to_thread(self.repository.write_save, payload)
            finally:
                self._queue.task_done()
