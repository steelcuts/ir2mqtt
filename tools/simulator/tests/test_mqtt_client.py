import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add project root to the Python path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools", "simulator"))


from tools.simulator.mqtt_client import CoreMqttClient  # noqa: E402


@pytest.fixture
def mqtt_client():
    """Pytest fixture for the CoreMqttClient."""
    with patch("tools.simulator.mqtt_client.mqtt_client.Client") as mock_paho_client:
        client = CoreMqttClient("localhost", 1883)
        client.client = mock_paho_client.return_value
        yield client


def test_on_connect_success(mqtt_client):
    """Test the _on_connect method with a successful connection."""
    mqtt_client.on_log_cb = MagicMock()
    mqtt_client.on_connection_change_cb = MagicMock()
    mqtt_client.publish_on_connect = [("topic", "payload", False)]

    mqtt_client._on_connect(None, None, None, 0)

    mqtt_client.on_log_cb.assert_called_with("MQTT", "Connected to localhost:1883", "INFO")
    mqtt_client.client.subscribe.assert_called_with("ir2mqtt/#")
    mqtt_client.on_connection_change_cb.assert_called_with(True, None)
    assert mqtt_client._connected_flag is True
    assert len(mqtt_client.publish_on_connect) == 0


def test_on_connect_failure(mqtt_client):
    """Test the _on_connect method with a failed connection."""
    mqtt_client.on_log_cb = MagicMock()
    mqtt_client.on_connection_change_cb = MagicMock()

    mqtt_client._on_connect(None, None, None, 1)

    mqtt_client.on_log_cb.assert_called_with("MQTT", f"Connection failed for {mqtt_client.client_id} with code 1", "ERROR")
    mqtt_client.on_connection_change_cb.assert_called_with(False, "Connection failed with code 1")


def test_on_disconnect(mqtt_client):
    """Test the _on_disconnect method."""
    mqtt_client.on_log_cb = MagicMock()
    mqtt_client.on_connection_change_cb = MagicMock()
    mqtt_client._connected_flag = True

    mqtt_client._on_disconnect(None, None, None, 0)

    mqtt_client.on_log_cb.assert_called_with("MQTT", f"Client {mqtt_client.client_id} disconnected", "WARN")
    assert mqtt_client._connected_flag is False
    mqtt_client.on_connection_change_cb.assert_called_with(False, None)


def test_on_message(mqtt_client):
    """Test the _on_message method."""
    mqtt_client.on_message_cb = MagicMock()
    msg = MagicMock()
    msg.topic = "test/topic"
    msg.payload = b"test_payload"
    msg.retain = False

    mqtt_client._on_message(None, None, msg)

    mqtt_client.on_message_cb.assert_called_with("test/topic", "test_payload", False)


def test_start(mqtt_client):
    """Test the start method."""
    mqtt_client.start()
    mqtt_client.client.connect_async.assert_called_with("localhost", 1883, 60)
    mqtt_client.client.loop_start.assert_called_once()


def test_stop(mqtt_client):
    """Test the stop method."""
    mqtt_client.stop()
    mqtt_client.client.loop_stop.assert_called_once()
    mqtt_client.client.disconnect.assert_called_once()


def test_publish(mqtt_client):
    """Test the publish method."""
    mqtt_client.publish("topic", "payload", True)
    mqtt_client.client.publish.assert_called_with("topic", "payload", retain=True)


def test_queue_publish_connected(mqtt_client):
    """Test the queue_publish method when connected."""
    mqtt_client._connected_flag = True
    mqtt_client.publish = MagicMock()

    mqtt_client.queue_publish("topic", "payload", True)

    mqtt_client.publish.assert_called_with("topic", "payload", True)
    assert len(mqtt_client.publish_on_connect) == 0


def test_queue_publish_disconnected(mqtt_client):
    """Test the queue_publish method when disconnected."""
    mqtt_client._connected_flag = False
    mqtt_client.publish = MagicMock()

    mqtt_client.queue_publish("topic", "payload", True)

    mqtt_client.publish.assert_not_called()
    assert mqtt_client.publish_on_connect == [("topic", "payload", True)]


def test_is_connected(mqtt_client):
    """Test the is_connected method."""
    mqtt_client.client.is_connected.return_value = True
    assert mqtt_client.is_connected() is True

    mqtt_client.client.is_connected.return_value = False
    assert mqtt_client.is_connected() is False


def test_publish_exception(mqtt_client):
    """Test publish method exception handling."""
    mqtt_client.client.publish.side_effect = Exception("Publish error")
    mqtt_client.on_log_cb = MagicMock()

    mqtt_client.publish("topic", "payload")

    mqtt_client.on_log_cb.assert_called_with("MQTT", "Publish failed: Publish error", "ERROR")
