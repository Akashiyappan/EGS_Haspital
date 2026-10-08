"""Realtime channel.

Protocol (JSON frames `{"type": ..., "data": ...}`):

- Client connects to `/api/v1/ws` and must send `{"type": "auth", "token": "<access token>"}`
  within AUTH_TIMEOUT seconds. Tokens are not put in the URL (it ends up in logs).
- Server replies `ready`. The socket is closed with code 4401 when the access token
  expires; the client refreshes it and reconnects, then catches up via REST
  (`GET /chat/conversations/{id}/messages?after_id=...`).
- Server events: `message.created`, `conversation.read`, `notification.created`,
  `presence`, `typing`, `pong`.
- Client events: `ping`, `typing` (`data.conversation_id`).
"""

import asyncio
import contextlib
import json
import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppError
from app.core.security import decode_token
from app.db.session import get_session_factory
from app.models import User
from app.realtime.manager import manager
from app.services import auth_service, chat_service

logger = logging.getLogger(__name__)

router = APIRouter()

AUTH_TIMEOUT = 10
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
MAX_FRAME_BYTES = 4096

SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


async def _authenticate(
    websocket: WebSocket, sessions: async_sessionmaker[AsyncSession]
) -> tuple[User, float] | None:
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT)
        frame = json.loads(raw)
        token = frame.get("token") if frame.get("type") == "auth" else None
        if not isinstance(token, str):
            raise ValueError("auth frame required")
        async with sessions() as db:
            user = await auth_service.resolve_token_user(db, token, "access")
        expires_at = float(decode_token(token, "access")["exp"])
    except (TimeoutError, ValueError, json.JSONDecodeError, AttributeError, AppError):
        await websocket.close(code=CLOSE_UNAUTHORIZED, reason="Authentication required")
        return None
    if user.must_change_password:
        await websocket.close(code=CLOSE_FORBIDDEN, reason="Password change required")
        return None
    return user, expires_at


async def _broadcast_presence(
    sessions: async_sessionmaker[AsyncSession], user: User, online: bool
) -> None:
    async with sessions() as db:
        recipients = await chat_service.counterpart_user_ids(db, user)
    await manager.send_to_users(recipients, "presence", chat_service.presence_payload(user, online))


async def _handle_typing(sessions: async_sessionmaker[AsyncSession], user: User, data: Any) -> None:
    conversation_id = data.get("conversation_id") if isinstance(data, dict) else None
    if not isinstance(conversation_id, int):
        return
    async with sessions() as db:
        try:
            conversation = await chat_service.get_for_user(db, conversation_id, user)
        except AppError:
            return  # not a participant: silently ignore
        recipient = chat_service.other_user_id(conversation, user)
    await manager.send_to_user(
        recipient, "typing", {"conversation_id": conversation_id, "user_id": user.id}
    )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, sessions: SessionFactory) -> None:
    await websocket.accept()
    auth = await _authenticate(websocket, sessions)
    if auth is None:
        return
    user, expires_at = auth

    if await manager.connect(user.id, websocket):
        await _broadcast_presence(sessions, user, True)
    await websocket.send_json({"type": "ready", "data": {"user_id": user.id}})

    try:
        while True:
            remaining = expires_at - time.time()
            if remaining <= 0:
                await websocket.close(code=CLOSE_UNAUTHORIZED, reason="Token expired")
                break
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
            except TimeoutError:
                continue  # loop re-checks expiry and closes
            if len(raw) > MAX_FRAME_BYTES:
                continue
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = frame.get("type") if isinstance(frame, dict) else None
            if kind == "ping":
                await websocket.send_json({"type": "pong", "data": {}})
            elif kind == "typing":
                await _handle_typing(sessions, user, frame.get("data"))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for user %s", user.id)
        with contextlib.suppress(Exception):  # the socket may already be closed
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
    finally:
        if await manager.disconnect(user.id, websocket):
            await _broadcast_presence(sessions, user, False)
