# backend/tests/test_mqtt.py

import asyncio
import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from backend.models import BridgeSettings, IRButton, IRCode, IRDevice
from backend.mqtt import MQTTManager
from backend.state import StateManager


@pytest.fixture
def state_manager():
    """Returns a new StateManager instance for each test."""
    return StateManager()


@pytest.fixture
def mqtt_manager(state_manager):
    """Returns a new MQTTManager instance for each test."""
    automation_manager = MagicMock()
    automation_manager.trigger_from_ha = MagicMock()
    manager = MQTTManager(state_manager, automation_manager)
    manager.client = MagicMock()
    manager.loop = MagicMock()
    manager.loop.is_running.return_value = True
    manager.logger = MagicMock()
    manager.settings = MagicMock()
    manager.settings.mqtt_broker = "core-mosquitto"
    manager.settings.mqtt_port = 1883
    manager.settings.mqtt_user = None
    manager.settings.mqtt_pass = None
    manager.settings.bridge_settings = {}
    return manager


@pytest.fixture(autouse=True)
def mock_broadcast_ws():
    with patch("backend.mqtt.broadcast_ws", new_callable=MagicMock) as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_run_coroutine_threadsafe():
    with patch("backend.mqtt.asyncio.run_coroutine_threadsafe") as mock:
        yield mock


@pytest.fixture
def mock_create_task():
    with patch("backend.mqtt.asyncio.create_task") as mock:
        yield mock


@patch("paho.mqtt.client.Client")
def test_mqtt_setup_default_broker(mock_mqtt_client, mqtt_manager: MQTTManager):
    mock_instance = mock_mqtt_client.return_value
    mqtt_manager.setup(mqtt_manager.loop, mqtt_manager.settings, mqtt_manager.logger)

    mqtt_manager.logger.error.assert_not_called()
    mock_mqtt_client.assert_called_once()
    mock_instance.username_pw_set.assert_not_called()
    assert mock_instance.on_connect is not None
    assert mock_instance.on_message is not None
    mock_instance.connect_async.assert_called_once_with("core-mosquitto", 1883, 60)
    mock_instance.loop_start.assert_called_once()


@patch("paho.mqtt.client.Client")
def test_mqtt_setup_no_broker(mock_mqtt_client, mqtt_manager: MQTTManager, monkeypatch):
    # Unset env var to test default connection.
    monkeypatch.delenv("MQTT_BROKER", raising=False)
    mqtt_manager.settings.mqtt_broker = None

    mqtt_manager.setup(mqtt_manager.loop, mqtt_manager.settings, mqtt_manager.logger)

    mock_mqtt_client.assert_not_called()


@patch("paho.mqtt.client.Client")
def test_mqtt_setup_with_env_vars(mock_mqtt_client, mqtt_manager: MQTTManager, monkeypatch):
    mqtt_manager.settings.mqtt_broker = "test.broker"
    mqtt_manager.settings.mqtt_port = 1234
    mqtt_manager.settings.mqtt_user = "testuser"
    mqtt_manager.settings.mqtt_pass = "testpass"

    mock_instance = mock_mqtt_client.return_value
    mqtt_manager.setup(mqtt_manager.loop, mqtt_manager.settings, mqtt_manager.logger)

    mqtt_manager.logger.error.assert_not_called()
    mock_mqtt_client.assert_called_once()
    mock_instance.username_pw_set.assert_called_once_with("testuser", "testpass")
    mock_instance.connect_async.assert_called_once_with("test.broker", 1234, 60)


def test_on_connect_success(mock_broadcast_ws, mqtt_manager: MQTTManager):
    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True
    mock_client = mqtt_manager.client
    coro = asyncio.sleep(0)
    on_connect_cb_mock = MagicMock()
    on_connect_cb_mock.return_value = coro
    mqtt_manager.on_connect_cb = on_connect_cb_mock

    with patch("backend.mqtt.asyncio.run_coroutine_threadsafe") as mock_run_coro:
        mqtt_manager.on_connect(mock_client, None, None, 0)

        assert mqtt_manager.connected is True
        mock_client.subscribe.assert_any_call("ir2mqtt/bridge/+/state")
        assert mock_run_coro.call_count == 2
        mock_run_coro.assert_any_call(ANY, mqtt_manager.loop)
        mock_run_coro.assert_any_call(coro, mqtt_manager.loop)
        mock_broadcast_ws.assert_called()
    coro.close()


def test_on_connect_fail(mock_broadcast_ws, mqtt_manager: MQTTManager):
    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True
    mock_client = mqtt_manager.client

    with patch("backend.mqtt.asyncio.run_coroutine_threadsafe") as mock_run_coro:
        mqtt_manager.on_connect(mock_client, None, None, 5)

        assert mqtt_manager.connected is False
        mock_run_coro.assert_called_once_with(ANY, mqtt_manager.loop)
        mock_broadcast_ws.assert_called()


def test_on_message_bridge_state(mock_broadcast_ws, mqtt_manager: MQTTManager):
    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True
    mock_msg = MagicMock()
    mock_msg.topic = "ir2mqtt/bridge/test-bridge/state"
    mock_msg.payload = b'{"online": true, "enabled_protocols": ["nec"]}'

    with patch.object(mqtt_manager, "_broadcast_bridges") as mock_broadcast:
        mqtt_manager.on_message(None, None, mock_msg)

        assert "test-bridge" in mqtt_manager.bridges
        assert mqtt_manager.bridges["test-bridge"]["online"] is True
        assert "nec" in mqtt_manager.bridges["test-bridge"]["enabled_protocols"]
        mock_broadcast.assert_called_once()


def test_on_message_learn_code(mock_broadcast_ws, mqtt_manager: MQTTManager, state_manager: StateManager):
    mqtt_manager.settings.echo_suppression_ms = 0
    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True
    state_manager.learning_bridges = ["any"]
    mqtt_manager.bridges["test-bridge"] = {}

    mock_msg = MagicMock()
    mock_msg.topic = "ir2mqtt/bridge/test-bridge/received"
    mock_msg.payload = b'{"protocol": "nec", "payload": {"data": "0x1234"}}'

    with patch.object(mqtt_manager, "_broadcast_bridges"):
        with patch("backend.mqtt.asyncio.run_coroutine_threadsafe") as mock_run_coro:
            mqtt_manager.on_message(None, None, mock_msg)

            assert state_manager.last_learned_code is not None
            assert state_manager.last_learned_code["protocol"] == "nec"
            assert state_manager.learning_bridges == ["any"]
            mock_run_coro.assert_called_once_with(ANY, mqtt_manager.loop)
            mock_broadcast_ws.assert_called_once()


@pytest.mark.asyncio
async def test_send_ir_code(mqtt_manager):
    mqtt_manager.connected = True
    mqtt_manager.bridges["br1"] = {"online": True}
    code = {"protocol": "nec", "payload": {"address": "0x1", "command": "0x2"}}

    with patch.object(mqtt_manager, "send_command", new_callable=AsyncMock) as mock_send_cmd:
        mock_send_cmd.return_value = {"success": True}
        await mqtt_manager.send_ir_code(code, target="br1")

        mock_send_cmd.assert_called_once()
        args = mock_send_cmd.call_args
        assert args[0][0] == "br1"
        assert args[0][1] == "send"
        assert args[0][2]["code"] == code


@pytest.mark.asyncio
async def test_send_ir_code_offline_target(mqtt_manager):
    mqtt_manager.connected = True
    mqtt_manager.bridges["br1"] = {"online": False}
    code = {"protocol": "nec", "payload": {"address": "0x1", "command": "0x2"}}

    with patch.object(mqtt_manager, "send_command", new_callable=AsyncMock) as mock_send_cmd:
        await mqtt_manager.send_ir_code(code, target="br1")
        mock_send_cmd.assert_not_called()


@pytest.mark.asyncio
async def test_send_ir_code_nonexistent_target(mqtt_manager):
    mqtt_manager.connected = True
    mqtt_manager.bridges["br1"] = {"online": True}
    code = {"protocol": "nec", "payload": {"address": "0x1", "command": "0x2"}}

    with patch.object(mqtt_manager, "send_command", new_callable=AsyncMock) as mock_send_cmd:
        await mqtt_manager.send_ir_code(code, target="br2")
        mock_send_cmd.assert_not_called()


@pytest.mark.asyncio
async def test_send_ir_code_broadcast(mqtt_manager):
    mqtt_manager.connected = True
    mqtt_manager.bridges["br1"] = {"online": True}
    mqtt_manager.bridges["br2"] = {"online": False}
    mqtt_manager.bridges["br3"] = {"online": True}
    code = {"protocol": "nec", "payload": {"address": "0x1", "command": "0x2"}}

    with patch.object(mqtt_manager, "send_command", new_callable=AsyncMock) as mock_send_cmd:
        mock_send_cmd.return_value = {"success": True}
        await mqtt_manager.send_ir_code(code, target="broadcast")

        assert mock_send_cmd.call_count == 2
        mock_send_cmd.assert_any_call("br1", "send", {"code": code})
        mock_send_cmd.assert_any_call("br3", "send", {"code": code})


def test_on_message_config(mqtt_manager):
    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True
    msg = MagicMock()
    msg.topic = "ir2mqtt/bridge/bridge1/config"
    msg.payload = b'{"name": "Bridge One", "ip": "1.2.3.4"}'

    with patch.object(mqtt_manager, "_broadcast_bridges") as mock_broadcast:
        mqtt_manager.on_message(None, None, msg)

        assert "bridge1" in mqtt_manager.bridges
        assert mqtt_manager.bridges["bridge1"]["ip"] == "1.2.3.4"
        assert mqtt_manager.bridges["bridge1"]["name"] == "Bridge One"
        mock_broadcast.assert_called_once()


def test_on_message_bridge_state_remove(mock_broadcast_ws, mqtt_manager):
    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True
    mqtt_manager.bridges["bridge1"] = {"online": True}
    msg = MagicMock()
    msg.topic = "ir2mqtt/bridge/bridge1/state"
    msg.payload = b""

    with patch.object(mqtt_manager, "_broadcast_bridges") as mock_broadcast:
        mqtt_manager.on_message(None, None, msg)

        assert "bridge1" not in mqtt_manager.bridges
        mock_broadcast.assert_called_once()


def test_on_message_received_empty_payload(mqtt_manager):
    # This simulates the clearing of retained messages when a bridge is deleted
    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True

    # Ensure bridge is NOT in memory
    if "br1" in mqtt_manager.bridges:
        del mqtt_manager.bridges["br1"]

    msg = MagicMock()
    msg.topic = "ir2mqtt/bridge/br1/received"
    msg.payload = b""

    with patch.object(mqtt_manager, "_handle_ir_received") as mock_handle:
        mqtt_manager.on_message(None, None, msg)

        # Should NOT call handle, thus NOT recreating the bridge
        mock_handle.assert_not_called()
        assert "br1" not in mqtt_manager.bridges


def test_on_message_ha_trigger(mqtt_manager):
    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True
    msg = MagicMock()
    msg.topic = "ir2mqtt/automation/auto1/trigger"
    msg.payload = b"PRESS"

    with patch("backend.mqtt.asyncio.run_coroutine_threadsafe") as mock_run:
        mqtt_manager.on_message(None, None, msg)

        mock_run.assert_called_once_with(
            mqtt_manager.automation_manager.trigger_from_ha.return_value,
            mqtt_manager.loop,
        )
        mqtt_manager.automation_manager.trigger_from_ha.assert_called_once_with("auto1")


def test_on_message_delegates_to_integration(mqtt_manager):
    mock_integration = MagicMock()
    mock_integration.handle_message.return_value = True  # Handled
    mqtt_manager.set_integration(mock_integration)

    msg = MagicMock()
    msg.topic = "ir2mqtt/some/topic"
    msg.payload = b"payload"

    mqtt_manager.on_message(None, None, msg)

    mock_integration.handle_message.assert_called_once_with("ir2mqtt/some/topic", "payload", mqtt_manager)


def test_on_message_publishes_events_via_integration(mock_broadcast_ws, mqtt_manager, state_manager):
    mqtt_manager.settings.echo_suppression_ms = 0
    # Setup device/button
    btn = IRButton(
        id="b1",
        name="Btn",
        code=IRCode(protocol="nec", payload={"data": "0x1"}),
        is_event=True,
        is_input=True,
    )
    dev = IRDevice(id="d1", name="Dev", buttons=[btn])
    state_manager.devices = [dev]

    mock_integration = MagicMock()
    mock_integration.handle_message.return_value = False
    mqtt_manager.set_integration(mock_integration)

    msg = MagicMock()
    msg.topic = "ir2mqtt/bridge/br1/received"
    msg.payload = b'{"protocol": "nec", "payload": {"data": "0x1"}}'

    # Mock loop to run immediately
    with patch("backend.mqtt.asyncio.run_coroutine_threadsafe"):
        mqtt_manager.on_message(None, None, msg)

    # Verify integration calls
    mock_integration.publish_button_event.assert_called_once_with(dev, btn, mqtt_manager)
    # Should publish ON because default input mode is momentary (or toggle logic handles it)
    mock_integration.publish_input_state.assert_called_once_with(dev, btn, "ON", mqtt_manager)


@pytest.mark.asyncio
async def test_test_connection_success(mqtt_manager):
    mqtt_manager.loop = asyncio.get_running_loop()
    with patch("paho.mqtt.client.Client") as mock_cls:
        mock_client = mock_cls.return_value

        def side_effect_connect(*args, **kwargs):
            if mock_client.on_connect:
                # Simulate success rc=0
                mock_client.on_connect(mock_client, None, None, 0)

        mock_client.connect.side_effect = side_effect_connect

        settings = {"broker": "host", "port": 1883}
        result = await mqtt_manager.test_connection(settings)
        assert result["status"] == "ok"
        mock_client.connect.assert_called_with("host", 1883, 5)


@pytest.mark.asyncio
async def test_test_connection_failure(mqtt_manager):
    mqtt_manager.loop = asyncio.get_running_loop()
    with patch("paho.mqtt.client.Client") as mock_cls:
        mock_client = mock_cls.return_value

        def side_effect_connect(*args, **kwargs):
            if mock_client.on_connect:
                # Simulate failure rc=5
                mock_client.on_connect(mock_client, None, None, 5)

        mock_client.connect.side_effect = side_effect_connect

        settings = {"broker": "host", "port": 1883}
        result = await mqtt_manager.test_connection(settings)

        assert result["status"] == "error"
        assert "code 5" in result["message"]


def test_disconnect(mqtt_manager):
    mock_client = MagicMock()
    mqtt_manager.client = mock_client
    mqtt_manager.connected = True
    mqtt_manager.disconnect()
    mock_client.disconnect.assert_called_once()
    assert mqtt_manager.connected is False
    assert mqtt_manager.client is None


@pytest.mark.asyncio
async def test_reload(mqtt_manager):
    with patch.object(mqtt_manager, "disconnect") as mock_disc:
        with patch.object(mqtt_manager, "connect") as mock_conn:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await mqtt_manager.reload()
                mock_disc.assert_called_once()
                mock_conn.assert_called_once()
                mock_sleep.assert_called_once_with(1)


def test_smart_learning_logic(mqtt_manager, state_manager):
    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True

    state_manager.learning_type = "smart"
    state_manager.current_burst = []
    state_manager.smart_samples = []

    # 1. Handle Smart Data (Accumulate burst)
    data1 = {"protocol": "nec", "payload": {"data": "0x1"}}
    with patch.object(mqtt_manager.loop, "call_later") as mock_call_later:
        mqtt_manager._handle_smart_data(data1, "bridge1")
        assert len(state_manager.current_burst) == 1
        assert state_manager.last_code_bridge == "bridge1"
        mock_call_later.assert_called()

    # 2. Process Burst
    state_manager.current_burst = [data1, data1]  # Burst of 2 identical codes

    with patch("backend.mqtt.broadcast_ws", new_callable=MagicMock):
        with patch("backend.mqtt.asyncio.create_task") as mock_task:
            mqtt_manager._process_burst()

            assert len(state_manager.smart_samples) == 1
            assert len(state_manager.current_burst) == 0
            # Should broadcast progress
            mock_task.assert_called()

            # Fill samples to target (4) and provide a burst for the 5th
            state_manager.smart_samples = [[data1]] * 4
            state_manager.current_burst = [data1]

            mqtt_manager._process_burst()  # Should finish
            assert state_manager.last_learned_code == data1
            assert state_manager.learning_bridges == []


def test_analyze_smart_samples(mqtt_manager):
    codeA = {"p": "nec", "d": "A"}
    codeB = {"p": "nec", "d": "B"}
    codeC = {"p": "nec", "d": "C"}

    samples = [[codeA, codeB], [codeA], [codeA, codeC]]

    result = mqtt_manager._analyze_smart_samples(samples)
    assert result == codeA


def test_on_message_received_matching(mqtt_manager, state_manager):
    mqtt_manager.settings.echo_suppression_ms = 0
    # Setup device with toggle button
    btn = IRButton(
        id="b1",
        name="Btn",
        code=IRCode(protocol="nec", data="0x1"),
        is_input=True,
        input_mode="toggle",
    )
    dev = IRDevice(id="d1", name="Dev", buttons=[btn])
    state_manager.devices = [dev]
    state_manager.input_states["b1"] = False

    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True
    mqtt_manager.integration = MagicMock()
    mqtt_manager.integration.handle_message.return_value = False

    msg = MagicMock()
    msg.topic = "ir2mqtt/bridge/br1/received"
    msg.payload = b'{"protocol": "nec", "data": "0x1"}'

    with patch("backend.mqtt.asyncio.run_coroutine_threadsafe"):
        mqtt_manager.on_message(None, None, msg)

        # Check toggle logic
        assert state_manager.input_states["b1"] is True
        mqtt_manager.integration.publish_input_state.assert_called_with(dev, btn, "ON", mqtt_manager)


@pytest.mark.asyncio
async def test_echo_suppression_comprehensive(mock_broadcast_ws, mqtt_manager, state_manager):
    # Setup basic mocks
    mqtt_manager.connected = True
    mqtt_manager.bridges["br1"] = {"online": True}
    mqtt_manager.bridges["br2"] = {"online": True}
    mqtt_manager.send_command = AsyncMock(return_value={"success": True})  # Is already async mock
    mqtt_manager.loop = MagicMock()
    mqtt_manager.loop.is_running.return_value = True
    mqtt_manager.integration = MagicMock()
    mqtt_manager.integration.handle_message.return_value = False

    code_a = {"protocol": "nec", "payload": {"address": "0x1", "command": "0x2"}}
    code_b = {"protocol": "nec", "payload": {"address": "0x1", "command": "0x3"}}

    # Helper function to run a test case
    async def run_case(mqtt_mgr, bridge_settings, tx_target, rx_bridge, sent_code, received_code, expect_suppressed, description):
        # Reset state
        state_manager.sent_codes_history = []
        mqtt_mgr.settings.bridge_settings = bridge_settings

        # 1. Send
        with patch("time.time", return_value=100.0):
            await mqtt_mgr.send_ir_code(sent_code, target=tx_target)

        # 2. Receive
        with patch("time.time", return_value=100.1):
            msg = MagicMock()
            msg.topic = f"ir2mqtt/bridge/{rx_bridge}/received"
            msg.payload = json.dumps(received_code).encode()

            # Setup device matching received code so integration would be called if not suppressed
            btn = IRButton(id="b1", name="Btn", code=IRCode(protocol=received_code["protocol"], payload=received_code.get("payload", {})), is_event=True)
            dev = IRDevice(id="d1", name="Dev", buttons=[btn])
            state_manager.devices = [dev]

            mqtt_mgr.integration.publish_button_event.reset_mock()

            with patch.object(mqtt_mgr, "_broadcast_bridges"):
                mqtt_mgr.on_message(None, None, msg)

                if expect_suppressed:
                    try:
                        mqtt_mgr.integration.publish_button_event.assert_not_called()
                    except AssertionError as e:
                        raise AssertionError(f"Failed case: {description}. Expected suppression, but event was published.") from e
                else:
                    try:
                        mqtt_mgr.integration.publish_button_event.assert_called()
                    except AssertionError as e:
                        raise AssertionError(f"Failed case: {description}. Expected event, but it was suppressed.") from e

    # --- Test Cases ---

    # 1. Bridge Settings: Disabled
    settings_disabled = {"br1": BridgeSettings(echo_enabled=False)}
    await run_case(mqtt_manager, settings_disabled, "br1", "br1", code_a, code_a, False, "Explicitly disabled")

    # 3. Bridge Settings: Enabled, Smart=True, IgnoreSelf=True (Standard Loopback)
    settings_std = {"br1": BridgeSettings(echo_enabled=True, echo_timeout=500, echo_smart=True, echo_ignore_self=True)}
    await run_case(mqtt_manager, settings_std, "br1", "br1", code_a, code_a, True, "Smart, Self, Matching Code")
    await run_case(mqtt_manager, settings_std, "br1", "br1", code_a, code_b, False, "Smart, Self, Different Code")

    # 4. Bridge Settings: Enabled, Smart=False (Blind), IgnoreSelf=True
    settings_blind = {"br1": BridgeSettings(echo_enabled=True, echo_timeout=500, echo_smart=False, echo_ignore_self=True)}
    await run_case(mqtt_manager, settings_blind, "br1", "br1", code_a, code_b, True, "Blind, Self, Different Code")

    # 5. Bridge Settings: IgnoreSelf=False
    settings_no_self = {"br1": BridgeSettings(echo_enabled=True, echo_timeout=500, echo_ignore_self=False)}
    await run_case(mqtt_manager, settings_no_self, "br1", "br1", code_a, code_a, False, "Ignore Self OFF")

    # 6. Bridge Settings: IgnoreOthers=True (Cross-Talk)
    # Settings apply to the RECEIVING bridge (br2)
    settings_cross = {"br2": BridgeSettings(echo_enabled=True, echo_timeout=500, echo_ignore_others=True)}
    await run_case(mqtt_manager, settings_cross, "br1", "br2", code_a, code_a, True, "Ignore Others ON, Cross-talk")

    # 7. Bridge Settings: IgnoreOthers=False (Default)
    settings_no_cross = {"br2": BridgeSettings(echo_enabled=True, echo_timeout=500, echo_ignore_others=False)}
    await run_case(mqtt_manager, settings_no_cross, "br1", "br2", code_a, code_a, False, "Ignore Others OFF, Cross-talk")

    # 8. Broadcast handling (Self)
    # Sending to broadcast means br1 is in targets. br1 receiving it should be treated as self.
    settings_broadcast = {"br1": BridgeSettings(echo_enabled=True, echo_timeout=500, echo_ignore_self=True)}
    await run_case(mqtt_manager, settings_broadcast, "broadcast", "br1", code_a, code_a, True, "Broadcast send, Self echo")


@pytest.mark.asyncio
async def test_send_command_flow(mqtt_manager):
    mqtt_manager.loop = asyncio.get_running_loop()
    mqtt_manager.connected = True

    # Start send_command task
    task = asyncio.create_task(mqtt_manager.send_command("br1", "cmd"))

    # Wait for request to be registered
    await asyncio.sleep(0.01)
    assert len(mqtt_manager.pending_requests) == 1
    req_id = list(mqtt_manager.pending_requests.keys())[0]

    # Simulate response
    msg = MagicMock()
    msg.topic = "ir2mqtt/bridge/br1/response"
    msg.payload = json.dumps({"request_id": req_id, "success": True}).encode()

    mqtt_manager.on_message(None, None, msg)

    res = await task
    assert res["success"] is True
    assert len(mqtt_manager.pending_requests) == 0


def test_on_message_malformed_json(mqtt_manager):
    msg = MagicMock()
    msg.topic = "ir2mqtt/bridge/br1/config"
    msg.payload = b"{bad_json"

    # Should not raise exception
    mqtt_manager.on_message(None, None, msg)
