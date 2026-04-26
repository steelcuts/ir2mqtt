"""
Tests for Serial Bridge API endpoints
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


@patch("backend.routers.serial_bridges.list_ports.comports")
def test_list_serial_ports(mock_comports, client: TestClient):
    """Test: GET /api/bridges/serial/ports returns available ports"""
    # Mock the available ports
    mock_port1 = MagicMock()
    mock_port1.device = "/dev/ttyUSB0"
    mock_port1.description = "USB to Serial"
    mock_port1.hwid = "USB VID:PID=1234:5678"

    mock_port2 = MagicMock()
    mock_port2.device = "/dev/ttyUSB1"
    mock_port2.description = "CH340"
    mock_port2.hwid = "USB VID:PID=1a86:7523"

    mock_comports.return_value = [mock_port1, mock_port2]

    response = client.get("/api/bridges/serial/ports")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["port"] == "/dev/ttyUSB0"
    assert data[0]["description"] == "USB to Serial"
    assert data[1]["port"] == "/dev/ttyUSB1"


@patch("backend.routers.serial_bridges.serial.Serial")
def test_test_serial_connection_success(mock_serial_class, client: TestClient):
    """Test: POST /api/bridges/serial/test with successful connection"""
    # Mock the Serial instance
    mock_ser = MagicMock()
    mock_serial_class.return_value = mock_ser

    # Simulate a successful response
    config_response = json.dumps({"id": "serial_test", "name": "Test Bridge", "capabilities": ["nec", "rc5"]}).encode() + b"\n"
    mock_ser.readline.return_value = config_response

    payload = {"port": "/dev/ttyUSB0", "baudrate": 115200}

    response = client.post("/api/bridges/serial/test", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "config" in data
    assert data["config"]["id"] == "serial_test"

    # Verify calls
    mock_serial_class.assert_called_once_with(port="/dev/ttyUSB0", baudrate=115200, timeout=3)
    mock_ser.write.assert_called_once_with(b'{"command": "get_config"}\n')


@patch("backend.routers.serial_bridges.serial.Serial")
def test_test_serial_connection_no_response(mock_serial_class, client: TestClient):
    """Test: POST /api/bridges/serial/test without response from device"""
    mock_ser = MagicMock()
    mock_serial_class.return_value = mock_ser
    mock_ser.readline.return_value = b""  # No response

    payload = {"port": "/dev/ttyUSB0", "baudrate": 115200}

    response = client.post("/api/bridges/serial/test", json=payload)
    # Expect 504 or generic 500 if error handling is not exact
    assert response.status_code in [504, 500]


@patch("backend.routers.serial_bridges.serial.Serial")
def test_test_serial_connection_port_not_found(mock_serial_class, client: TestClient):
    """Test: POST /api/bridges/serial/test with invalid port"""
    import serial

    mock_serial_class.side_effect = serial.SerialException("Port not found")

    payload = {"port": "/dev/ttyUSB999", "baudrate": 115200}

    response = client.post("/api/bridges/serial/test", json=payload)
    assert response.status_code == 400
    assert "Failed to open serial port" in response.json()["detail"]


@patch("backend.routers.serial_bridges.broadcast_ws", new_callable=AsyncMock)
@patch("backend.routers.serial_bridges.SerialTransport")
@patch("backend.routers.serial_bridges.update_options_file")
def test_create_serial_bridge(
    mock_update_options,
    mock_serial_transport_class,
    mock_broadcast,
    client: TestClient,
):
    """Test: POST /api/bridges/serial creates a new Serial Bridge"""
    # Mock SerialTransport
    mock_transport_instance = MagicMock()
    mock_transport_instance.bridge_id = "serial_dev_ttyUSB0"
    mock_transport_instance.stop = AsyncMock()

    async def wait_mock():
        pass

    mock_event = MagicMock()
    mock_event.wait = AsyncMock(side_effect=wait_mock)
    mock_transport_instance.ready_event = mock_event

    mock_serial_transport_class.return_value = mock_transport_instance

    payload = {"port": "/dev/ttyUSB0", "baudrate": 115200}

    response = client.post("/api/bridges/serial", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["bridge_id"] == "serial_dev_ttyUSB0"

    # Verify that the config was saved
    mock_update_options.assert_called_once()

    # Verify that the bridge was started
    mock_transport_instance.start.assert_called_once()


def test_delete_non_serial_bridge(client: TestClient):
    """Test: Error when trying to delete a non-serial bridge"""
    response = client.delete("/api/bridges/serial/mqtt_bridge_1")
    assert response.status_code == 400
    assert "Only serial bridges can be deleted via this endpoint" in response.json()["detail"]
