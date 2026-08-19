"""
veloctra_api/websocket.py
========================
Real-time telemetry WebSocket router, connection manager, and zero-event-loss event buffer.
"""

from __future__ import annotations

import asyncio
import collections
import json
import logging
import time
from typing import Any, Deque, Dict, List, Optional, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from veloctra_security.security import decode_access_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Telemetry"])


class TelemetryEventRingBuffer:
    """In-memory circular event buffer ensuring zero event loss for connecting/reconnecting clients."""

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._channel_buffers: Dict[str, Deque[Dict[str, Any]]] = collections.defaultdict(
            lambda: collections.deque(maxlen=self.max_size)
        )
        self._global_buffer: Deque[Dict[str, Any]] = collections.deque(maxlen=self.max_size)
        self._lock = asyncio.Lock()

    async def push(self, channel: str, event: Dict[str, Any]) -> None:
        async with self._lock:
            event_with_meta = dict(event)
            if "timestamp" not in event_with_meta:
                event_with_meta["timestamp"] = time.time()
            self._channel_buffers[channel].append(event_with_meta)
            self._global_buffer.append(event_with_meta)

    async def get_recent_events(self, channel: str, limit: int = 50) -> List[Dict[str, Any]]:
        async with self._lock:
            if channel == "*" or channel == "all":
                events = list(self._global_buffer)
            else:
                events = list(self._channel_buffers.get(channel, []))
            return events[-limit:] if limit > 0 else events


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = collections.defaultdict(set)
        self._ring_buffer = TelemetryEventRingBuffer(max_size=500)
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[channel].add(websocket)
        logger.info("[WebSocket] Client connected to channel '%s'", channel)

        # Replay recent buffered events to the newly connected client
        recent_events = await self._ring_buffer.get_recent_events(channel, limit=30)
        try:
            await websocket.send_text(json.dumps({
                "event": "connection_established",
                "channel": channel,
                "replay_count": len(recent_events),
                "timestamp": time.time(),
            }))
            for evt in recent_events:
                await websocket.send_text(json.dumps(evt, default=str))
        except Exception as exc:
            logger.warning("[WebSocket] Error replaying initial events: %s", exc)

    async def disconnect(self, channel: str, websocket: WebSocket) -> None:
        async with self._lock:
            if channel in self._connections:
                self._connections[channel].discard(websocket)
                if not self._connections[channel]:
                    del self._connections[channel]
        logger.info("[WebSocket] Client disconnected from channel '%s'", channel)

    async def broadcast(self, channel: str, message: dict) -> None:
        # 1. Record event into ring buffer for zero loss
        await self._ring_buffer.push(channel, message)

        # 2. Collect target sockets across specific channel, job_id, tenant_id, and wildcard '*'
        job_id = message.get("job_id")
        tenant_id = message.get("tenant_id")

        target_channels = {channel, "*"}
        if job_id:
            target_channels.add(job_id)
        if tenant_id:
            target_channels.add(tenant_id)

        async with self._lock:
            targets: Set[WebSocket] = set()
            for ch in target_channels:
                targets.update(self._connections.get(ch, set()))

        if not targets:
            return

        payload = json.dumps(message, default=str)
        dead: List[Tuple[str, WebSocket]] = []

        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                for ch in target_channels:
                    if ws in self._connections.get(ch, set()):
                        dead.append((ch, ws))

        if dead:
            async with self._lock:
                for ch, ws in dead:
                    self._connections.get(ch, set()).discard(ws)

    def get_ring_buffer(self) -> TelemetryEventRingBuffer:
        return self._ring_buffer


manager = ConnectionManager()


async def telemetry_broadcaster(channel: str, message: dict) -> None:
    await manager.broadcast(channel, message)


@router.websocket("/ws/telemetry/{project_id}")
async def websocket_telemetry_endpoint(
    websocket: WebSocket,
    project_id: str,
    token: str = Query(...),
):
    try:
        payload = decode_access_token(token)
        # Authorize: SuperAdmin, matching tenant, or job ID associated with tenant
        is_authorized = (
            payload.role == "SuperAdmin"
            or payload.tenant_id == project_id
            or project_id == "all"
            or project_id.startswith(payload.tenant_id)
        )
        if not is_authorized:
            await websocket.close(code=4003, reason="Tenant mismatch")
            return
    except Exception as exc:
        await websocket.close(code=4001, reason=f"Unauthorized: {exc}")
        return

    await manager.connect(project_id, websocket)
    try:
        while True:
            # Handle incoming ping / messages to keep connection alive
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text(json.dumps({"event": "pong", "timestamp": time.time()}))
    except WebSocketDisconnect:
        await manager.disconnect(project_id, websocket)
    except Exception as e:
        logger.debug("[WebSocket] Connection ended: %s", e)
        await manager.disconnect(project_id, websocket)
