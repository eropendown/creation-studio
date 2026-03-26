import asyncio, json
from fastapi import WebSocket

class WSManager:
    def __init__(self):
        self._c: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, jid: str, ws: WebSocket):
        await ws.accept()
        async with self._lock: self._c.setdefault(jid, set()).add(ws)

    async def disconnect(self, jid: str, ws: WebSocket):
        async with self._lock:
            s = self._c.get(jid, set()); s.discard(ws)
            if not s: self._c.pop(jid, None)

    async def broadcast(self, jid: str, data: dict):
        msg = json.dumps(data, ensure_ascii=False)
        dead = []
        for ws in list(self._c.get(jid, set())):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(jid, ws)

manager = WSManager()