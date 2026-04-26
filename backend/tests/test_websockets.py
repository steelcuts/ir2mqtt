import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.websockets import broadcast_ws, log_broadcaster, ws_clients


@pytest.fixture(autouse=True)
def cleanup_ws_clients():
    yield
    ws_clients.clear()


@pytest.mark.asyncio
async def test_log_broadcaster():
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws_clients.add(ws)

    new_queue = asyncio.Queue()

    with patch("backend.websockets.log_queue", new_queue):
        await new_queue.put("test log")

        task = asyncio.create_task(log_broadcaster())
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    ws.send_json.assert_called_with({"type": "log", "message": "test log"})


@pytest.mark.asyncio
async def test_broadcast_ws():
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws_clients.add(ws)

    await broadcast_ws({"type": "test"})

    ws.send_json.assert_called_with({"type": "test"})


@pytest.mark.asyncio
async def test_broadcast_ws_error():
    ws = MagicMock()
    ws.send_json = AsyncMock(side_effect=Exception("fail"))
    ws_clients.add(ws)

    await broadcast_ws({"type": "test"})

    assert ws not in ws_clients
