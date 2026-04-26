import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.automations import InactivityState
from backend.models import IRAutomation, IRAutomationTrigger, IRButton, IRCode, IRDevice


def test_get_automations_empty(client: TestClient, automation_manager):
    automation_manager.automations = []
    response = client.get("/api/automations")
    assert response.status_code == 200
    assert response.json() == []


def test_create_automation(client: TestClient, automation_manager):
    automation_manager.automations = []
    payload = {
        "name": "Test Auto",
        "triggers": [{"type": "single", "device_id": "dev1", "button_id": "btn1"}],
        "actions": [
            {"type": "delay", "delay_ms": 500},
            {"type": "ir_send", "device_id": "dev1", "button_id": "btn2"},
        ],
    }
    # Mock save to avoid file writes.
    with patch.object(automation_manager, "save", return_value=None):
        response = client.post("/api/automations", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Auto"
        assert "id" in data
        assert data["ordering"] == 1
        assert len(data["actions"]) == 2
        assert len(automation_manager.automations) == 1
        assert automation_manager.automations[0].ordering == 1

        payload2 = {"name": "Test Auto 2", "triggers": [], "actions": []}
        response2 = client.post("/api/automations", json=payload2)
        data2 = response2.json()
        assert data2["ordering"] == 2
        assert automation_manager.automations[1].ordering == 2


@pytest.mark.asyncio
async def test_update_automation(client: TestClient, automation_manager):
    auto = IRAutomation(
        id="auto1",
        name="Old Name",
        triggers=[IRAutomationTrigger(type="single", device_id="d1", button_id="b1")],
    )
    # Save to DB first so update finds it
    await automation_manager.add_automation(auto)

    payload = {
        "id": "auto1",
        "name": "New Name",
        "triggers": [{"type": "single", "device_id": "d1", "button_id": "b1"}],
        "actions": [],
    }

    response = client.put("/api/automations/auto1", json=payload)
    assert response.status_code == 200
    assert automation_manager.automations[0].name == "New Name"


@pytest.mark.asyncio
async def test_delete_automation(client: TestClient, automation_manager):
    auto = IRAutomation(
        id="auto1",
        name="To Delete",
        triggers=[IRAutomationTrigger(type="single", device_id="d1", button_id="b1")],
    )
    await automation_manager.add_automation(auto)

    response = client.delete("/api/automations/auto1")
    assert response.status_code == 200
    assert len(automation_manager.automations) == 0


@pytest.mark.asyncio
async def test_delete_automation_cleans_up_state(client: TestClient, automation_manager):
    auto = IRAutomation(id="auto1", name="To Delete", triggers=[{}])
    await automation_manager.add_automation(auto)

    automation_manager.automation_locks["auto1"] = "lock"
    automation_manager.multi_press_state["auto1_0"] = "state"
    automation_manager.sequence_state["auto1_0"] = "state"
    automation_manager.sequence_last_time["auto1_0"] = "state"

    await automation_manager.delete_automation("auto1")

    assert len(automation_manager.automations) == 0
    assert "auto1" not in automation_manager.automation_locks
    assert "auto1_0" not in automation_manager.multi_press_state
    assert "auto1_0" not in automation_manager.sequence_state
    assert "auto1_0" not in automation_manager.sequence_last_time


@pytest.mark.asyncio
async def test_run_automation_logic(client, automation_manager, mqtt_manager, state_manager):
    # Setup State.
    dev = IRDevice(
        id="dev1",
        name="TV",
        buttons=[
            IRButton(
                id="btn1",
                name="Power",
                code=IRCode(protocol="NEC", address="0x1", command="0x2"),
            )
        ],
    )
    state_manager.devices = [dev]

    send_ir_mock = AsyncMock()

    auto = IRAutomation(
        id="auto1",
        name="Test",
        triggers=[IRAutomationTrigger(type="single", device_id="trigger_dev", button_id="trigger_btn")],
        actions=[
            {"type": "delay", "delay_ms": 10},
            {
                "type": "ir_send",
                "device_id": "dev1",
                "button_id": "btn1",
                "target": "bridge1",
            },
        ],
    )

    mqtt_manager.integration = MagicMock()

    await automation_manager.run_automation(auto, state_manager, send_ir_mock)

    send_ir_mock.assert_called_once()
    call_args = send_ir_mock.call_args
    assert call_args[0][0]["protocol"] == "NEC"
    assert call_args[1]["target"] == "bridge1"


@pytest.mark.asyncio
async def test_process_trigger_matches(client, automation_manager, state_manager):
    automation_manager.automations = [
        IRAutomation(
            id="auto1",
            name="Match",
            enabled=True,
            triggers=[IRAutomationTrigger(type="single", device_id="dev1", button_id="btn1")],
        ),
        IRAutomation(
            id="auto2",
            name="No Match",
            enabled=True,
            triggers=[IRAutomationTrigger(type="single", device_id="dev1", button_id="btn2")],
        ),
    ]

    with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
        await automation_manager._handle_ir_event(
            {
                "matches": [("dev1", "btn1")],
                "state_manager": state_manager,
                "send_ir_func": MagicMock(),
                "timestamp": 100.0,
            }
        )

        assert mock_run.call_count == 1
        args, _ = mock_run.call_args
        assert args[0].id == "auto1"


@pytest.mark.asyncio
async def test_process_trigger_multi_press(client, automation_manager, state_manager):
    automation_manager.automations = [
        IRAutomation(
            id="auto_multi",
            name="Multi Trigger",
            enabled=True,
            triggers=[
                IRAutomationTrigger(
                    type="multi",
                    device_id="dev1",
                    button_id="btn1",
                    count=3,
                    window_ms=1000,
                )
            ],
        )
    ]
    automation_manager.multi_press_state = {}

    with patch("backend.automations.time.time") as mock_time:
        with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
            # 1st press.
            mock_time.return_value = 100.0
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.0,
                }
            )
            assert mock_run.call_count == 0

            # 2nd press.
            mock_time.return_value = 100.2
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.2,
                }
            )
            assert mock_run.call_count == 0

            # 3rd press (Trigger).
            mock_time.return_value = 100.4
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.4,
                }
            )
            assert mock_run.call_count == 1

            # 4th press (Should start new window, count reset).
            mock_run.reset_mock()
            mock_time.return_value = 100.6
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.6,
                }
            )
            assert mock_run.call_count == 0


@pytest.mark.asyncio
async def test_process_trigger_sequence(client, automation_manager, state_manager):
    automation_manager.automations = [
        IRAutomation(
            id="auto_seq",
            name="Seq Trigger",
            enabled=True,
            triggers=[
                IRAutomationTrigger(
                    type="sequence",
                    sequence=[
                        {"device_id": "dev1", "button_id": "btn1"},
                        {"device_id": "dev1", "button_id": "btn2"},
                    ],
                    window_ms=1000,
                )
            ],
        )
    ]
    automation_manager.sequence_state = {}
    automation_manager.sequence_last_time = {}

    with patch("backend.automations.time.time") as mock_time:
        with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
            # Step 1.
            mock_time.return_value = 100.0
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.0,
                }
            )
            assert mock_run.call_count == 0

            # Wrong Step (Reset).
            mock_time.return_value = 100.2
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn3")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.2,
                }
            )
            assert mock_run.call_count == 0

            # Step 1 again.
            mock_time.return_value = 100.4
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.4,
                }
            )
            assert mock_run.call_count == 0

            # Step 2 (Trigger).
            mock_time.return_value = 100.6
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn2")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.6,
                }
            )
            assert mock_run.call_count == 1

            # Test Timeout.
            mock_run.reset_mock()
            # Step 1.
            mock_time.return_value = 200.0
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 200.0,
                }
            )

            # Step 2 (Too late, > 1000ms).
            mock_time.return_value = 202.0
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn2")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 202.0,
                }
            )
            assert mock_run.call_count == 0


@pytest.mark.asyncio
async def test_process_trigger_strict_mode(client, automation_manager, state_manager):
    # 1. Test Multi-Press Strict Mode (Default: True).
    automation_manager.automations = [
        IRAutomation(
            id="auto_strict",
            name="Strict Multi",
            enabled=True,
            triggers=[
                IRAutomationTrigger(
                    type="multi",
                    device_id="dev1",
                    button_id="btn1",
                    count=3,
                    window_ms=1000,
                    reset_on_other_input=True,
                )
            ],
        )
    ]
    automation_manager.multi_press_state = {}

    with patch("backend.automations.time.time") as mock_time:
        with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
            # Press 1.
            mock_time.return_value = 100.0
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.0,
                }
            )
            assert len(automation_manager.multi_press_state["auto_strict_0"]) == 1

            # Press Wrong Button.
            mock_time.return_value = 100.1
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn2")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.1,
                }
            )
            # Should be reset.
            assert len(automation_manager.multi_press_state.get("auto_strict_0", [])) == 0

    # 2. Test Multi-Press Loose Mode (False).
    automation_manager.automations = [
        IRAutomation(
            id="auto_loose",
            name="Loose Multi",
            enabled=True,
            triggers=[
                IRAutomationTrigger(
                    type="multi",
                    device_id="dev1",
                    button_id="btn1",
                    count=2,
                    window_ms=1000,
                    reset_on_other_input=False,
                )
            ],
        )
    ]
    automation_manager.multi_press_state = {}

    with patch("backend.automations.time.time") as mock_time:
        with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
            # Press 1.
            mock_time.return_value = 100.0
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.0,
                }
            )

            # Press Wrong Button.
            mock_time.return_value = 100.1
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn2")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.1,
                }
            )
            # Should NOT be reset.
            assert len(automation_manager.multi_press_state["auto_loose_0"]) == 1

            # Press 2 (Trigger).
            mock_time.return_value = 100.2
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.2,
                }
            )
            assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_reorder(automation_manager):
    a1 = IRAutomation(id="1", name="A1")
    a2 = IRAutomation(id="2", name="A2")
    a3 = IRAutomation(id="3", name="A3")
    automation_manager.automations = [a1, a2, a3]

    with patch.object(automation_manager, "save"):
        await automation_manager.reorder(["3", "1"])

        assert len(automation_manager.automations) == 3
        assert automation_manager.automations[0].id == "3"
        assert automation_manager.automations[1].id == "1"
        assert automation_manager.automations[2].id == "2"


@pytest.mark.asyncio
async def test_load_save(client, automation_manager):
    # Create automation in DB
    auto = IRAutomation(id="1", name="A1")
    await automation_manager.add_automation(auto)

    # Clear memory
    automation_manager.automations = []

    # Load from DB
    await automation_manager.load()

    assert len(automation_manager.automations) == 1
    assert automation_manager.automations[0].name == "A1"


def test_start_stop(client, automation_manager):
    with patch("asyncio.create_task"):
        automation_manager.start()
        assert automation_manager.worker_task is not None

        # Stop.
        mock_worker = MagicMock()
        automation_manager.worker_task = mock_worker
        automation_manager.stop()
        mock_worker.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_process_trigger_sequence_loose(client, automation_manager, state_manager):
    # 3. Test Sequence Loose Mode.
    automation_manager.automations = [
        IRAutomation(
            id="auto_seq_loose",
            name="Loose Seq",
            enabled=True,
            triggers=[
                IRAutomationTrigger(
                    type="sequence",
                    sequence=[
                        {"device_id": "dev1", "button_id": "btn1"},
                        {"device_id": "dev1", "button_id": "btn2"},
                    ],
                    window_ms=1000,
                    reset_on_other_input=False,
                )
            ],
        )
    ]
    automation_manager.sequence_state = {}
    automation_manager.sequence_last_time = {}

    with patch("backend.automations.time.time") as mock_time:
        with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
            # Step 1.
            mock_time.return_value = 100.0
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn1")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.0,
                }
            )
            assert automation_manager.sequence_state["auto_seq_loose_0"] == 1

            # Wrong Button.
            mock_time.return_value = 100.1
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn3")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.1,
                }
            )
            # Should NOT be reset.
            assert automation_manager.sequence_state["auto_seq_loose_0"] == 1

            # Step 2.
            mock_time.return_value = 100.2
            await automation_manager._handle_ir_event(
                {
                    "matches": [("dev1", "btn2")],
                    "state_manager": state_manager,
                    "send_ir_func": MagicMock(),
                    "timestamp": 100.2,
                }
            )
            assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_run_automation_state_publishing(client, automation_manager, state_manager):
    # Setup
    auto = IRAutomation(id="auto1", name="Test", actions=[{"type": "delay", "delay_ms": 10}])

    mock_mqtt = MagicMock()
    mock_integration = MagicMock()
    mock_mqtt.integration = mock_integration
    automation_manager.set_mqtt_manager(mock_mqtt)

    # Run
    await automation_manager.run_automation(auto, state_manager, MagicMock())

    # Verify
    assert mock_integration.publish_automation_state.call_count == 2
    # Should publish ON at start
    mock_integration.publish_automation_state.assert_any_call(auto, "ON", mock_mqtt)
    # Should publish OFF at end
    mock_integration.publish_automation_state.assert_any_call(auto, "OFF", mock_mqtt)


@pytest.mark.asyncio
async def test_automation_timeouts(automation_manager):
    # Setup a multi-press trigger that should time out
    multi_trigger = IRAutomationTrigger(type="multi", device_id="d1", button_id="b1", count=3, window_ms=1000)
    # Setup a sequence trigger that should time out
    seq_trigger = IRAutomationTrigger(type="sequence", sequence=[{"device_id": "d1", "button_id": "b1"}], window_ms=1000)

    automation_manager.automations = [
        IRAutomation(id="multi_auto", name="Multi", triggers=[multi_trigger]),
        IRAutomation(id="seq_auto", name="Seq", triggers=[seq_trigger]),
    ]

    # 1. Test _get_next_timeout
    with patch("time.time", return_value=100.0):
        # Add a press to the multi-press state
        automation_manager.multi_press_state["multi_auto_0"] = [99.5]  # 0.5s ago
        # Add a step to the sequence state
        automation_manager.sequence_state["seq_auto_0"] = 1
        automation_manager.sequence_last_time["seq_auto_0"] = 99.8  # 0.2s ago

        # The multi-press expires at 99.5 + 1.0 = 100.5 (0.5s from now)
        # The sequence expires at 99.8 + 1.0 = 100.8 (0.8s from now)
        # So the next timeout should be ~0.5s
        next_timeout = automation_manager._get_next_timeout()
        assert next_timeout is not None
        assert 0.4 < next_timeout < 0.6

    # 2. Test _check_timeouts
    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock) as mock_ws:
        with patch("time.time", return_value=101.0):  # Time has advanced past the timeout
            await automation_manager._check_timeouts()

            # Both states should be cleared
            assert automation_manager.multi_press_state["multi_auto_0"] == []
            assert automation_manager.sequence_state["seq_auto_0"] == 0
            # Check that websockets were called to update UI
            assert mock_ws.call_count == 2


@pytest.mark.asyncio
async def test_run_automation_parallelism(automation_manager, state_manager):
    import asyncio

    # Setup
    auto_serial = IRAutomation(id="a1", name="Serial", allow_parallel=False, actions=[{"type": "delay", "delay_ms": 50}])
    auto_parallel = IRAutomation(id="a2", name="Parallel", allow_parallel=True, actions=[{"type": "delay", "delay_ms": 50}])

    # 1. Test non-parallel (default)
    start_time = time.time()
    task1 = asyncio.create_task(automation_manager.run_automation(auto_serial, state_manager, AsyncMock()))
    task2 = asyncio.create_task(automation_manager.run_automation(auto_serial, state_manager, AsyncMock()))
    await asyncio.gather(task1, task2)
    assert (time.time() - start_time) > 0.08  # ~100ms (allow some jitter)

    # 2. Test parallel
    start_time_p = time.time()
    task3 = asyncio.create_task(automation_manager.run_automation(auto_parallel, state_manager, AsyncMock()))
    task4 = asyncio.create_task(automation_manager.run_automation(auto_parallel, state_manager, AsyncMock()))
    await asyncio.gather(task3, task4)
    assert (time.time() - start_time_p) < 0.09  # ~50ms


@pytest.mark.asyncio
async def test_run_automation_event_publishing(client, automation_manager, state_manager):
    # Setup
    auto = IRAutomation(id="auto1", name="Test", actions=[{"type": "event", "event_name": "MyEvent"}])

    mock_mqtt = MagicMock()
    mock_integration = MagicMock()
    mock_mqtt.integration = mock_integration
    automation_manager.set_mqtt_manager(mock_mqtt)

    # Run
    await automation_manager.run_automation(auto, state_manager, MagicMock())

    # Verify
    mock_integration.publish_automation_event.assert_called_once()
    args = mock_integration.publish_automation_event.call_args[0]
    assert args[0] == auto
    assert args[1] == "MyEvent"
    # args[2] is run_id (random), args[3] is mqtt_manager
    assert args[3] == mock_mqtt


# ---------------------------------------------------------------------------
# device_inactivity trigger tests
# ---------------------------------------------------------------------------


def _make_inactivity_auto(
    auto_id="auto_inact",
    device_id="dev1",
    timeout_s=0.1,
    watch_mode="received",
    button_filter=None,
    button_exclude=None,
    rearm_mode="always",
    cooldown_s=0.0,
    require_initial_activity=True,
    ignore_own_actions=True,
) -> IRAutomation:
    """Helper that builds an IRAutomation with a device_inactivity trigger."""
    return IRAutomation(
        id=auto_id,
        name="Inactivity Test",
        enabled=True,
        triggers=[
            IRAutomationTrigger(
                type="device_inactivity",
                device_id=device_id,
                timeout_s=timeout_s,
                watch_mode=watch_mode,
                button_filter=button_filter,
                button_exclude=button_exclude,
                rearm_mode=rearm_mode,
                cooldown_s=cooldown_s,
                require_initial_activity=require_initial_activity,
                ignore_own_actions=ignore_own_actions,
            )
        ],
        actions=[{"type": "delay", "delay_ms": 1}],
    )


@pytest.mark.asyncio
async def test_inactivity_trigger_fires_after_timeout(automation_manager, state_manager, mqtt_manager):
    """Activity arms the timer; after the timeout the automation fires."""
    auto = _make_inactivity_auto(timeout_s=0.05)
    automation_manager.automations = [auto]
    automation_manager.set_mqtt_manager(mqtt_manager)
    mqtt_manager.integration = MagicMock()

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
            await automation_manager.notify_device_activity("dev1", "btn1", "received")

            # Timer is now running — automation should not have fired yet
            assert mock_run.call_count == 0

            # Wait long enough for the timer to expire
            await asyncio.sleep(0.15)
            assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_inactivity_timer_resets_on_new_activity(automation_manager, state_manager, mqtt_manager):
    """Each new activity event cancels and restarts the timer."""
    auto = _make_inactivity_auto(timeout_s=0.08)
    automation_manager.automations = [auto]
    automation_manager.set_mqtt_manager(mqtt_manager)
    mqtt_manager.integration = MagicMock()

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
            # First activity
            await automation_manager.notify_device_activity("dev1", "btn1", "received")
            await asyncio.sleep(0.05)

            # Second activity before the first timeout — should reset the clock
            await automation_manager.notify_device_activity("dev1", "btn1", "received")
            await asyncio.sleep(0.05)

            # Still within the second window, should not have fired
            assert mock_run.call_count == 0

            # Now wait for the second timer to expire
            await asyncio.sleep(0.1)
            assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_inactivity_wrong_device_ignored(automation_manager, state_manager):
    """Activity on a different device must not arm the timer."""
    auto = _make_inactivity_auto(device_id="dev1", timeout_s=0.05)
    automation_manager.automations = [auto]

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        await automation_manager.notify_device_activity("dev_other", "btn1", "received")

    state = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state is None or not state.armed


@pytest.mark.asyncio
async def test_inactivity_watch_mode_received_only(automation_manager, state_manager):
    """watch_mode='received' must ignore 'sent' events."""
    auto = _make_inactivity_auto(watch_mode="received", timeout_s=0.05)
    automation_manager.automations = [auto]

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        # Sent event — should not arm
        await automation_manager.notify_device_activity("dev1", "btn1", "sent")

    state = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state is None or not state.armed


@pytest.mark.asyncio
async def test_inactivity_watch_mode_sent_only(automation_manager, state_manager):
    """watch_mode='sent' must ignore 'received' events."""
    auto = _make_inactivity_auto(watch_mode="sent", timeout_s=0.05)
    automation_manager.automations = [auto]

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        # Received event — should not arm
        await automation_manager.notify_device_activity("dev1", "btn1", "received")

    state = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state is None or not state.armed


@pytest.mark.asyncio
async def test_inactivity_button_whitelist(automation_manager, state_manager):
    """Only whitelisted buttons should arm the timer."""
    auto = _make_inactivity_auto(button_filter=["btn_ok"], timeout_s=0.05)
    automation_manager.automations = [auto]

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        # Non-whitelisted button
        await automation_manager.notify_device_activity("dev1", "btn_other", "received")

    state = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state is None or not state.armed

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        # Whitelisted button
        await automation_manager.notify_device_activity("dev1", "btn_ok", "received")

    state = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state is not None and state.armed


@pytest.mark.asyncio
async def test_inactivity_button_blacklist(automation_manager, state_manager):
    """Blacklisted buttons must not arm the timer."""
    auto = _make_inactivity_auto(button_exclude=["btn_power"], timeout_s=0.05)
    automation_manager.automations = [auto]

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        # Blacklisted button
        await automation_manager.notify_device_activity("dev1", "btn_power", "received")

    state = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state is None or not state.armed

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        # Non-blacklisted button — should arm
        await automation_manager.notify_device_activity("dev1", "btn_vol", "received")

    state = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state is not None and state.armed


@pytest.mark.asyncio
async def test_inactivity_ignore_own_actions(automation_manager, state_manager):
    """Sent events from the same automation must not arm when ignore_own_actions=True."""
    auto = _make_inactivity_auto(watch_mode="both", ignore_own_actions=True, timeout_s=0.05)
    automation_manager.automations = [auto]

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        # Self-generated sent event
        await automation_manager.notify_device_activity("dev1", "btn1", "sent", source_automation_id="auto_inact")

    state = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state is None or not state.armed


@pytest.mark.asyncio
async def test_inactivity_rearm_mode_never(automation_manager, state_manager, mqtt_manager):
    """rearm_mode='never' fires once then permanently disarms the trigger."""
    auto = _make_inactivity_auto(timeout_s=0.05, rearm_mode="never")
    automation_manager.automations = [auto]
    automation_manager.set_mqtt_manager(mqtt_manager)
    mqtt_manager.integration = MagicMock()

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
            # First activity → arm → fire
            await automation_manager.notify_device_activity("dev1", "btn1", "received")
            await asyncio.sleep(0.15)
            assert mock_run.call_count == 1

            # Second activity → should be ignored (permanently disarmed)
            mock_run.reset_mock()
            await automation_manager.notify_device_activity("dev1", "btn1", "received")
            await asyncio.sleep(0.15)
            assert mock_run.call_count == 0


@pytest.mark.asyncio
async def test_inactivity_rearm_mode_cooldown(automation_manager, state_manager, mqtt_manager):
    """rearm_mode='cooldown' blocks re-arming until the cooldown expires."""
    auto = _make_inactivity_auto(timeout_s=0.05, rearm_mode="cooldown", cooldown_s=0.1)
    automation_manager.automations = [auto]
    automation_manager.set_mqtt_manager(mqtt_manager)
    mqtt_manager.integration = MagicMock()

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
            # First cycle: arm → fire
            await automation_manager.notify_device_activity("dev1", "btn1", "received")
            await asyncio.sleep(0.12)
            assert mock_run.call_count == 1

            # Immediately try to arm again — still in cooldown
            mock_run.reset_mock()
            await automation_manager.notify_device_activity("dev1", "btn1", "received")
            await asyncio.sleep(0.12)
            # Should NOT have fired (cooldown blocks it)
            assert mock_run.call_count == 0

            # Wait for cooldown to expire, then arm again
            await asyncio.sleep(0.1)
            await automation_manager.notify_device_activity("dev1", "btn1", "received")
            await asyncio.sleep(0.12)
            assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_inactivity_delete_cancels_timer(automation_manager):
    """Deleting an automation cancels any running inactivity timer."""
    auto = _make_inactivity_auto(timeout_s=10.0)  # Long timeout
    await automation_manager.add_automation(auto)
    automation_manager.automations[-1].enabled = True  # Ensure it's enabled

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        await automation_manager.notify_device_activity("dev1", "btn1", "received")

    state = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state is not None and state.armed and state.timer_task is not None

    await automation_manager.delete_automation("auto_inact")

    # State should have been cleaned up
    assert ("auto_inact", 0) not in automation_manager.inactivity_states


@pytest.mark.asyncio
async def test_inactivity_require_initial_activity_false(automation_manager, state_manager, mqtt_manager):
    """require_initial_activity=False starts the timer immediately on load."""
    auto = _make_inactivity_auto(timeout_s=0.05, require_initial_activity=False)
    automation_manager.automations = [auto]
    automation_manager.set_mqtt_manager(mqtt_manager)
    mqtt_manager.integration = MagicMock()

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        with patch.object(automation_manager, "run_automation", new_callable=AsyncMock) as mock_run:
            # Simulate the load() call which starts timers for non-initial-activity triggers
            for a in automation_manager.automations:
                if not a.enabled:
                    continue
                for t_idx, t in enumerate(a.triggers):
                    if t.type == "device_inactivity" and not t.require_initial_activity:
                        state_key = (a.id, t_idx)
                        state = InactivityState(armed=True)
                        automation_manager.inactivity_states[state_key] = state
                        state.timer_task = asyncio.create_task(automation_manager._inactivity_timer(a.id, t_idx, t.timeout_s))

            # Without any activity, the timer should fire on its own
            await asyncio.sleep(0.15)
            assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_inactivity_update_cancels_and_resets_timer(automation_manager, mqtt_manager):
    """Updating an automation cancels its running inactivity timer and restarts it
    for require_initial_activity=False triggers."""
    auto = _make_inactivity_auto(timeout_s=10.0)
    await automation_manager.add_automation(auto)
    automation_manager.set_mqtt_manager(mqtt_manager)

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        # Arm the timer via activity
        await automation_manager.notify_device_activity("dev1", "btn1", "received")

    state_before = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state_before is not None and state_before.armed

    old_task = state_before.timer_task

    # Update the automation — timer must be cancelled and state cleared
    updated = _make_inactivity_auto(timeout_s=20.0)
    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        await automation_manager.update_automation(updated)

    # Yield to the event loop so the CancelledError is delivered and the task finishes
    await asyncio.sleep(0)

    # The timer coroutine catches CancelledError internally and returns normally,
    # so the task ends as done() rather than cancelled().
    assert old_task.done()
    # State for the trigger should have been removed (require_initial_activity=True,
    # so no new timer is started until the next activity event)
    assert ("auto_inact", 0) not in automation_manager.inactivity_states


@pytest.mark.asyncio
async def test_inactivity_disabled_automation_timer_cancelled_on_update(automation_manager, mqtt_manager):
    """Setting enabled=False on an automation cancels its inactivity timer."""
    auto = _make_inactivity_auto(timeout_s=10.0)
    await automation_manager.add_automation(auto)
    automation_manager.set_mqtt_manager(mqtt_manager)

    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        await automation_manager.notify_device_activity("dev1", "btn1", "received")

    state_before = automation_manager.inactivity_states.get(("auto_inact", 0))
    assert state_before is not None and state_before.armed
    old_task = state_before.timer_task

    # Disable the automation via update
    disabled = _make_inactivity_auto(timeout_s=10.0)
    disabled.enabled = False
    with patch("backend.automations.broadcast_ws", new_callable=AsyncMock):
        await automation_manager.update_automation(disabled)

    # Yield to the event loop so the CancelledError is delivered and the task finishes
    await asyncio.sleep(0)

    # The timer coroutine catches CancelledError internally and returns normally,
    # so the task ends as done() rather than cancelled().
    assert old_task.done()
    assert ("auto_inact", 0) not in automation_manager.inactivity_states


def test_inactivity_trigger_invalid_watch_mode():
    """watch_mode must be one of received / sent / both."""
    with pytest.raises(Exception):
        IRAutomationTrigger(type="device_inactivity", watch_mode="all")


def test_inactivity_trigger_invalid_rearm_mode():
    """rearm_mode must be one of always / cooldown / never."""
    with pytest.raises(Exception):
        IRAutomationTrigger(type="device_inactivity", rearm_mode="loop")


def test_inactivity_trigger_zero_timeout():
    """timeout_s must be greater than 0."""
    with pytest.raises(Exception):
        IRAutomationTrigger(type="device_inactivity", timeout_s=0)


def test_inactivity_trigger_negative_timeout():
    """Negative timeout_s is rejected."""
    with pytest.raises(Exception):
        IRAutomationTrigger(type="device_inactivity", timeout_s=-5)
