from fastapi import WebSocket

from .config import log_queue

# --- WEBSOCKETS ---
ws_clients: set[WebSocket] = set()


async def broadcast_ws(msg: dict):
    for ws in list(ws_clients):
        try:
            await ws.send_json(msg)
        except Exception:
            ws_clients.discard(ws)


async def log_broadcaster():
    """Consumes logs from the queue and broadcasts them to all connected clients."""
    while True:
        entry = await log_queue.get()
        if ws_clients:
            for ws in list(ws_clients):
                try:
                    await ws.send_json({"type": "log", "message": entry})
                except Exception:
                    pass
        log_queue.task_done()
