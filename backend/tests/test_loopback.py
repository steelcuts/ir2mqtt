import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.loopback import run_loopback_test
from backend.state import StateManager


@pytest.fixture
def state_manager():
    return StateManager()


@pytest.fixture
def mqtt_manager():
    mm = MagicMock()
    mm.bridges = {
        "tx_bridge": {"capabilities": ["nec"]},
        "rx_bridge": {"capabilities": ["nec"], "protocols": {"nec": True}},
    }
    mm.publish = MagicMock()
    mm.send_ir_code = AsyncMock()
    mm.bridge_manager = MagicMock()
    mm.bridge_manager.send_command = AsyncMock(return_value={"success": True})
    return mm


@pytest.mark.asyncio
async def test_run_loopback_test_success(state_manager, mqtt_manager):
    with patch("backend.loopback.broadcast_ws", new_callable=AsyncMock) as mock_broadcast:
        task = asyncio.create_task(run_loopback_test("tx_bridge", "rx_bridge", mqtt_manager, state_manager))

        await asyncio.sleep(1.2)
        mqtt_manager.send_ir_code.assert_called()

        received_code = {"protocol": "nec", "payload": {"address": "0x1", "command": "0xBF"}}
        if state_manager.test_queue:
            await state_manager.test_queue.put(received_code)

        await task

        calls = [c[0][0] for c in mock_broadcast.call_args_list]
        types = [c["type"] for c in calls]
        assert "test_start" in types
        assert "test_progress" in types
        assert "test_end" in types

        progress_msg = next(c for c in calls if c["type"] == "test_progress")
        assert progress_msg["status"] == "passed"


@pytest.mark.asyncio
async def test_run_loopback_test_timeout(state_manager, mqtt_manager):
    with patch("backend.loopback.broadcast_ws", new_callable=AsyncMock) as mock_broadcast:
        with patch(
            "backend.loopback.TEST_CASES",
            [{"protocol": "nec", "payload": {"address": "0x1", "command": "0xBF"}}],
        ):

            async def mock_wait_for(fut, timeout=None):
                if asyncio.iscoroutine(fut):
                    fut.close()
                raise TimeoutError()

            with patch("asyncio.wait_for", side_effect=mock_wait_for):
                await run_loopback_test("tx_bridge", "rx_bridge", mqtt_manager, state_manager)

            calls = [c[0][0] for c in mock_broadcast.call_args_list]
            progress_msg = next((c for c in calls if c["type"] == "test_progress"), None)
            assert progress_msg
            assert progress_msg["status"] == "failed"


@pytest.mark.asyncio
async def test_run_loopback_test_cancelled(state_manager, mqtt_manager):
    with patch("backend.loopback.broadcast_ws", new_callable=AsyncMock) as mock_broadcast:
        task = asyncio.create_task(run_loopback_test("tx_bridge", "rx_bridge", mqtt_manager, state_manager))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        calls = [c[0][0] for c in mock_broadcast.call_args_list]
        types = [c["type"] for c in calls]
        assert "test_end" in types


@pytest.mark.asyncio
async def test_run_loopback_test_already_running(state_manager, mqtt_manager):
    state_manager.test_mode = True
    await run_loopback_test("tx_bridge", "rx_bridge", mqtt_manager, state_manager)
    mqtt_manager.send_ir_code.assert_not_called()
