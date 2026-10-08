"""In-process WebSocket connection registry.

The database is the source of truth: realtime events are a delivery
optimisation, and clients re-sync missed messages over REST after reconnecting.
This registry is per process; when running several workers, put a pub/sub
broker (e.g. Redis) behind `send_to_user` so events reach every worker.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> bool:
        """Register a socket. Returns True if this is the user's first connection."""
        async with self._lock:
            first = not self._connections[user_id]
            self._connections[user_id].add(websocket)
            return first

    async def disconnect(self, user_id: int, websocket: WebSocket) -> bool:
        """Unregister a socket. Returns True if the user has no connections left."""
        async with self._lock:
            sockets = self._connections.get(user_id)
            if not sockets:
                return False
            sockets.discard(websocket)
            if not sockets:
                del self._connections[user_id]
                return True
            return False

    def is_online(self, user_id: int) -> bool:
        return bool(self._connections.get(user_id))

    async def send_to_user(self, user_id: int, event: str, data: dict[str, Any]) -> None:
        sockets = list(self._connections.get(user_id, ()))
        if not sockets:
            return
        payload = {"type": event, "data": data}
        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:  # the socket is gone; its reader loop will clean up too
                logger.info("Dropping stale websocket for user %s", user_id)
                stale.append(socket)
        for socket in stale:
            await self.disconnect(user_id, socket)

    async def send_to_users(self, user_ids: list[int], event: str, data: dict[str, Any]) -> None:
        for user_id in set(user_ids):
            await self.send_to_user(user_id, event, data)

    def reset(self) -> None:
        self._connections.clear()


manager = ConnectionManager()
