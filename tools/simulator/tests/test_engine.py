import os
import sys
from unittest.mock import ANY, MagicMock, patch

import pytest

# Add project root to the Python path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools", "simulator"))


from tools.simulator.engine import SimulatorEngine  # noqa: E402


@pytest.fixture
def engine():
    """Pytest fixture for the SimulatorEngine."""
    on_log = MagicMock()
    on_bridges_updated = MagicMock()
    return SimulatorEngine("localhost", 1883, on_log, on_bridges_updated)


@patch("tools.simulator.engine.CoreMqttClient")
def test_spawn_and_add_bridge(mock_mqtt_client, engine):
    """Test the spawn_bridges and add_bridge methods."""
    engine.spawn_bridges(1)
    assert len(engine.bridges) == 1
    assert len(engine.clients) == 1
    engine.on_bridges_updated.assert_called()
    mock_mqtt_client.assert_called()


@patch("tools.simulator.engine.CoreMqttClient")
def test_delete_bridge(mock_mqtt_client, engine):
    """Test the delete_bridge method."""
    engine.spawn_bridges(1)
    bridge_id = engine.bridges[0].id

    mock_main_client = MagicMock()
    engine.main_mqtt_client = mock_main_client
    engine.delete_bridge(bridge_id)

    assert len(engine.bridges) == 0
    assert len(engine.clients) == 0
    mock_main_client.publish.assert_called()
    engine.on_bridges_updated.assert_called()


@patch("tools.simulator.engine.CoreMqttClient")
def test_delete_all_bridges(mock_mqtt_client, engine):
    """Test the delete_all_bridges method."""
    engine.spawn_bridges(3)
    assert len(engine.bridges) == 3

    # Mock main client to avoid actual MQTT calls if needed
    engine.main_mqtt_client = MagicMock()

    engine.delete_all_bridges()

    assert len(engine.bridges) == 0
    assert len(engine.clients) == 0
    engine.on_bridges_updated.assert_called()


@patch("tools.simulator.engine.CoreMqttClient")
def test_rename_bridge(mock_mqtt_client, engine):
    """Test the rename_bridge method."""
    engine.spawn_bridges(1)
    bridge_id = engine.bridges[0].id
    client_mock = engine.clients[bridge_id]

    engine.rename_bridge(bridge_id, "New Name")

    assert engine.get_bridge_by_id(bridge_id).name == "New Name"
    client_mock.publish.assert_called_with(f"ir2mqtt/bridge/{bridge_id}/config", ANY, True)
    engine.on_bridges_updated.assert_called()


def test_handle_message_config(engine):
    """Test the handle_message method with a config message."""
    engine.is_running = True
    topic = "ir2mqtt/bridge/sim-bridge-1234/config"
    payload = '{"name": "Test Bridge"}'

    engine.handle_message(topic, payload)

    bridge = engine.get_bridge_by_id("sim-bridge-1234")
    assert bridge is not None
    assert bridge.name == "Test Bridge"
    engine.on_bridges_updated.assert_called()


def test_handle_message_state(engine):
    """Test the handle_message method with a state message."""
    engine.is_running = True
    topic = "ir2mqtt/bridge/sim-bridge-1234/state"
    payload = '{"online": true}'

    engine.handle_message(topic, payload)

    bridge = engine.get_bridge_by_id("sim-bridge-1234")
    assert bridge is not None
    assert bridge.online is True
    engine.on_bridges_updated.assert_called()


@patch("tools.simulator.engine.CoreMqttClient")
def test_process_command_set_protocols(mock_mqtt_client, engine):
    """Test the _process_command method with 'set_protocols'."""
    engine.spawn_bridges(1)
    bridge_id = engine.bridges[0].id
    client_mock = engine.clients[bridge_id]
    payload = '{"command": "set_protocols", "protocols": ["nec", "sony"], "request_id": "123"}'

    engine._process_command(bridge_id, payload)

    assert engine.get_bridge_by_id(bridge_id).enabled_protocols == ["nec", "sony"]
    client_mock.publish.assert_any_call(f"ir2mqtt/bridge/{bridge_id}/response", '{"type": "response", "request_id": "123", "success": true}')
    client_mock.publish.assert_any_call(f"ir2mqtt/bridge/{bridge_id}/state", '{"online": true, "enabled_protocols": ["nec", "sony"]}', retain=True)
    engine.on_bridges_updated.assert_called()


@patch("tools.simulator.engine.CoreMqttClient")
def test_update_protocols(mock_mqtt_client, engine):
    """Test the update_protocols method."""
    engine.spawn_bridges(1)
    bridge_id = engine.bridges[0].id
    client_mock = engine.clients[bridge_id]

    new_protocols = ["nec", "rc5"]
    engine.update_protocols(bridge_id, new_protocols)

    # Check internal state
    bridge = engine.get_bridge_by_id(bridge_id)
    assert bridge.enabled_protocols == new_protocols

    # Check config update (using Pydantic model access)
    config = next((c for c in engine.simulated_configs if c.bid == bridge_id), None)
    assert config.protocols == new_protocols

    # Check MQTT publication
    client_mock.publish.assert_called_with(f"ir2mqtt/bridge/{bridge_id}/state", '{"online": true, "enabled_protocols": ["nec", "rc5"]}', retain=True)
    engine.on_bridges_updated.assert_called()


@patch("tools.simulator.engine.CoreMqttClient")
def test_process_command_send(mock_mqtt_client, engine):
    """Test the _process_command method with 'send'."""
    engine.spawn_bridges(1)
    bridge_id = engine.bridges[0].id
    client_mock = engine.clients[bridge_id]
    payload = '{"command": "send", "code": {"protocol": "nec"}, "request_id": "456"}'

    engine._process_command(bridge_id, payload)

    engine.on_log.assert_called_with("SIM", f"Bridge {bridge_id} received 'send' command for transmitter(s) any.", "DEBUG")
    client_mock.publish.assert_called_with(f"ir2mqtt/bridge/{bridge_id}/response", '{"type": "response", "request_id": "456", "success": true}')


@patch("tools.simulator.engine.CoreMqttClient")
def test_inject_signal(mock_mqtt_client, engine):
    """Test the inject_signal method."""
    engine.spawn_bridges(1)
    bridge_id = engine.bridges[0].id
    client_mock = engine.clients[bridge_id]
    payload = {"protocol": "nec", "address": "0x10", "command": "0x20", "receiver_id": "ir_rx_0"}

    engine.inject_signal(bridge_id, payload)

    client_mock.publish.assert_called_with(f"ir2mqtt/bridge/{bridge_id}/received", '{"protocol": "nec", "address": "0x10", "command": "0x20", "receiver_id": "ir_rx_0"}')


@patch("tools.simulator.engine.CoreMqttClient")
def test_inject_random_nec(mock_mqtt_client, engine):
    """Test the inject_random_nec method."""
    engine.spawn_bridges(1)
    bridge_id = engine.bridges[0].id
    client_mock = engine.clients[bridge_id]

    with patch("tools.simulator.engine.generate_random_hex", side_effect=["0xAA", "0xBB"]):
        engine.inject_random_nec(bridge_id)

    client_mock.publish.assert_called_with(
        f"ir2mqtt/bridge/{bridge_id}/received", '{"protocol": "nec", "payload": {"address": "0xAA", "command": "0xBB"}, "receiver_id": "ir_rx_0"}'
    )


@patch("tools.simulator.engine.CoreMqttClient")
def test_stop_simulation_and_shutdown(mock_mqtt_client, engine):
    """Test the stop_simulation and shutdown methods."""
    engine.spawn_bridges(1)
    bridge_id = engine.bridges[0].id
    client_mock = engine.clients[bridge_id]
    client_mock.is_connected.return_value = True

    engine.shutdown()

    assert engine.is_running is False
    client_mock.publish.assert_called_with(f"ir2mqtt/bridge/{bridge_id}/state", '{"online": false}', retain=True)
    client_mock.stop.assert_called()
    assert len(engine.clients) == 0
    assert len(engine.bridges) == 0
    engine.on_bridges_updated.assert_called()


def test_load_config_error(engine):
    """Test load_config with invalid file."""
    with patch("builtins.open", side_effect=Exception("File error")):
        engine.load_config()
        engine.on_log.assert_called_with("SIM", "Failed to load config: File error", "ERROR")


def test_save_config_error(engine):
    """Test save_config with write error."""
    # Mock open to raise an exception
    with patch("builtins.open", side_effect=Exception("Write error")):
        engine.save_config()
        engine.on_log.assert_called_with("SIM", "Failed to save config: Write error", "ERROR")
