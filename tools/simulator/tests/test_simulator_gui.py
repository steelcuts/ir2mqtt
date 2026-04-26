import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QWidget

# Add project root to the Python path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
from backend.models import IRButton, IRCode  # noqa: E402
from tools.simulator.engine import BridgeState  # noqa: E402
from tools.simulator.simulator_core import DeviceController, sanitize_topic  # noqa: E402
from tools.simulator.simulator_gui import BridgeSimulator, Controller, LogEntry, LogViewer, MainWindow, MqttSignals, SimulatorEngine, Tools  # noqa: E402


@pytest.fixture
def app(qapp):
    """Pytest fixture for a an application."""
    return qapp


def test_log_viewer_matches_filter(app):
    """Test the matches_filter method of the LogViewer widget."""
    viewer = LogViewer()

    # Test case 1: Empty filter
    viewer.filter_input.setText("")
    entry = LogEntry(time="12:00:00", topic="test/topic", payload="test payload", source="test_source", level="INFO", retained=False)
    assert viewer.matches_filter(entry) is True

    # Test case 2: Matching filter (topic)
    viewer.filter_input.setText("topic")
    assert viewer.matches_filter(entry) is True

    # Test case 3: Matching filter (payload)
    viewer.filter_input.setText("payload")
    assert viewer.matches_filter(entry) is True

    # Test case 4: Matching filter (source)
    viewer.filter_input.setText("source")
    assert viewer.matches_filter(entry) is True

    # Test case 5: Non-matching filter
    viewer.filter_input.setText("non-matching")
    assert viewer.matches_filter(entry) is False

    # Test case 6: Case-insensitive matching
    viewer.filter_input.setText("TOPIC")
    assert viewer.matches_filter(entry) is True


def test_log_viewer_add_and_clear(app):
    """Test adding and clearing logs in the LogViewer."""
    viewer = LogViewer()
    viewer.add_log("test_source", "test/topic", "test payload")
    assert viewer.table.rowCount() == 1
    assert len(viewer.logs) == 1

    viewer.clear_logs()
    assert viewer.table.rowCount() == 0
    assert len(viewer.logs) == 0


def test_log_viewer_filter(app):
    """Test filtering in the LogViewer."""
    viewer = LogViewer()
    viewer.add_log("source1", "topic1", "payload1")
    viewer.add_log("source2", "topic2", "payload2")

    assert viewer.table.rowCount() == 2

    viewer.filter_input.setText("topic1")
    viewer.apply_filter()
    assert viewer.table.rowCount() == 1
    assert viewer.table.item(0, 1).text() == "source1"

    viewer.filter_input.setText("payload2")
    viewer.apply_filter()
    assert viewer.table.rowCount() == 1
    assert viewer.table.item(0, 1).text() == "source2"


@pytest.fixture
def bridge_sim(app):
    """Pytest fixture for the BridgeSimulator widget."""
    signals = MqttSignals()
    engine = MagicMock(spec=SimulatorEngine)
    engine.bridges = []
    widget = BridgeSimulator(signals, engine)
    return widget


def test_bridge_sim_spawn(bridge_sim, qtbot):
    """Test the spawn bridges button."""
    bridge_sim.count_spin.setValue(3)
    qtbot.mouseClick(bridge_sim.create_btn, Qt.MouseButton.LeftButton)
    bridge_sim.engine.spawn_bridges.assert_called_once_with(3, rx_count=1, tx_count=1)


def test_bridge_sim_delete(bridge_sim, qtbot):
    """Test the delete bridge button."""
    bridge_sim.engine.bridges = [BridgeState(id="bridge1", ip="1.2.3.4", name="Bridge 1", online=True)]
    bridge_sim.refresh_bridge_list()
    item = bridge_sim.bridge_list.topLevelItem(0)
    bridge_sim.bridge_list.setCurrentItem(item)

    qtbot.mouseClick(bridge_sim.findChild(QWidget, "delete_bridge_btn"), Qt.MouseButton.LeftButton)
    bridge_sim.engine.delete_bridge.assert_called_once_with("bridge1")


def test_bridge_sim_delete_all(bridge_sim, qtbot):
    """Test the delete all bridges button."""
    # Mock QMessageBox to return Yes
    with patch("PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
        bridge_sim.delete_all_bridges()
        bridge_sim.engine.delete_all_bridges.assert_called_once()


def test_bridge_sim_delete_all_cancel(bridge_sim, qtbot):
    """Test canceling the delete all bridges button."""
    # Mock QMessageBox to return No
    with patch("PyQt6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
        bridge_sim.delete_all_bridges()
        bridge_sim.engine.delete_all_bridges.assert_not_called()


def test_bridge_sim_toggle_loopback(bridge_sim):
    """Test toggling loopback."""
    bridge_sim.loopback_chk.setChecked(True)
    assert bridge_sim.engine.loopback_enabled is True
    bridge_sim.loopback_chk.setChecked(False)
    assert bridge_sim.engine.loopback_enabled is False


def test_bridge_sim_inject_random(bridge_sim):
    """Test inject random NEC."""
    # Setup a bridge so get_selected_bridge_id returns something
    bridge_sim.engine.bridges = [BridgeState(id="bridge1", ip="1.2.3.4", name="Bridge 1", online=True)]
    bridge_sim.refresh_bridge_list()
    # Select the item
    bridge_sim.bridge_list.setCurrentItem(bridge_sim.bridge_list.topLevelItem(0))

    bridge_sim.inject_random()

    bridge_sim.engine.inject_random_nec.assert_called_with("bridge1")


def test_get_current_payload_nec(bridge_sim):
    """Test get_current_payload with the NEC protocol."""
    bridge_sim.proto_combo.setCurrentText("nec")
    bridge_sim.inputs["address"].setText("0x10")
    bridge_sim.inputs["command"].setText("0x20")

    payload = bridge_sim.get_current_payload()

    assert payload == {"protocol": "nec", "payload": {"address": "0x10", "command": "0x20"}}


def test_get_current_payload_samsung_with_defaults(bridge_sim):
    """Test get_current_payload with the Samsung protocol and default values."""
    bridge_sim.proto_combo.setCurrentText("samsung")
    bridge_sim.inputs["data"].setText("0x30")
    # nbits is not set, so it should use the default value

    payload = bridge_sim.get_current_payload()

    assert payload == {"protocol": "samsung", "payload": {"data": "0x30", "nbits": "32"}}


def test_get_current_payload_raw_json(bridge_sim):
    """Test get_current_payload with the RAW protocol and JSON data."""
    bridge_sim.proto_combo.setCurrentText("raw")
    bridge_sim.inputs["data"].setText('{"data": [1, 2, 3]}')

    payload = bridge_sim.get_current_payload()

    assert payload == {"protocol": "raw", "payload": {"data": {"data": [1, 2, 3]}}}


def test_get_current_payload_invalid_hex(bridge_sim):
    """Test get_current_payload with an invalid hex value."""
    bridge_sim.proto_combo.setCurrentText("nec")
    bridge_sim.inputs["address"].setText("not-a-hex-value")
    bridge_sim.inputs["command"].setText("0x20")

    with pytest.raises(ValueError, match="Address: for address must be a hex value."):
        bridge_sim.get_current_payload()


def test_get_current_payload_missing_field(bridge_sim):
    """Test get_current_payload with a missing field."""
    bridge_sim.proto_combo.setCurrentText("nec")
    bridge_sim.inputs["address"].setText("0x10")
    # command is not set

    with pytest.raises(ValueError, match="Field 'command' cannot be empty for protocol 'nec'."):
        bridge_sim.get_current_payload()


def test_get_current_payload_invalid_json(bridge_sim):
    """Test get_current_payload with invalid JSON data."""
    bridge_sim.proto_combo.setCurrentText("raw")
    bridge_sim.inputs["data"].setText("not-a-json-string")

    with pytest.raises(ValueError, match="Field 'data' must be valid JSON."):
        bridge_sim.get_current_payload()


@pytest.fixture
def controller_widget(app):
    """Pytest fixture for the Controller widget."""
    signals = MqttSignals()
    engine = MagicMock(spec=SimulatorEngine)
    engine.bridges = []
    device_ctrl = MagicMock(spec=DeviceController)
    widget = Controller(signals, engine, device_ctrl)
    return widget


def test_simulate_physical(controller_widget):
    """Test the simulate_physical method."""
    controller_widget.bridge_combo.addItem("bridge1", "bridge1_id")
    controller_widget.bridge_combo.setCurrentIndex(0)

    mock_code = IRCode(protocol="nec", address="0x10", command="0x20")
    data = {"btn": IRButton(id="btn1", name="btn1", code=mock_code)}

    controller_widget.simulate_physical(data)

    controller_widget.engine.inject_signal.assert_called_once_with("bridge1_id", mock_code.model_dump(exclude_none=True))


def test_send_ha_cmd(controller_widget):
    """Test the send_ha_cmd method."""
    mock_client = MagicMock()
    controller_widget.engine.main_mqtt_client = mock_client
    data = {"dev": MagicMock(id="dev1"), "btn": MagicMock(id="btn1")}

    controller_widget.send_ha_cmd(data)

    mock_client.publish.assert_called_once_with("ir2mqtt/cmd/dev1/btn1", "PRESS")


def test_send_sa_cmd(controller_widget):
    """Test the send_sa_cmd method."""
    mock_client = MagicMock()
    controller_widget.engine.main_mqtt_client = mock_client
    dev_mock = MagicMock()
    dev_mock.name = "My Device"
    btn_mock = MagicMock()
    btn_mock.name = "My Button"
    data = {"dev": dev_mock, "btn": btn_mock}

    controller_widget.send_sa_cmd(data)

    sanitized_dev_name = sanitize_topic(dev_mock.name)
    sanitized_btn_name = sanitize_topic(btn_mock.name)

    mock_client.publish.assert_called_once_with(f"ir2mqtt/devices/{sanitized_dev_name}/{sanitized_btn_name}/in", "PRESS")


def test_trigger_auto_by_id(controller_widget):
    """Test the trigger_auto method by ID."""
    mock_client = MagicMock()
    controller_widget.engine.main_mqtt_client = mock_client
    auto_mock = MagicMock(id="auto1")

    controller_widget.trigger_auto(auto_mock, "id")

    mock_client.publish.assert_called_once_with("ir2mqtt/automation/auto1/trigger", "PRESS")


def test_trigger_auto_by_name(controller_widget):
    """Test the trigger_auto method by name."""
    mock_client = MagicMock()
    controller_widget.engine.main_mqtt_client = mock_client
    auto_mock = MagicMock()
    auto_mock.name = "My Automation"

    controller_widget.trigger_auto(auto_mock, "name")

    sanitized_auto_name = sanitize_topic(auto_mock.name)

    mock_client.publish.assert_called_once_with(f"ir2mqtt/automations/{sanitized_auto_name}/trigger", "PRESS")


def test_controller_refresh_bridges(controller_widget):
    """Test the refresh_bridges method."""
    controller_widget.engine.bridges = [
        BridgeState(id="bridge1", ip="1.2.3.4", name="Bridge 1"),
        BridgeState(id="bridge2", ip="1.2.3.5", name="Bridge 2"),
    ]
    controller_widget.refresh_bridges()
    assert controller_widget.bridge_combo.count() == 2
    assert controller_widget.bridge_combo.itemText(0) == "Bridge 1 (bridge1)"


def test_controller_load_data_folder(controller_widget):
    """Test load_data_folder."""
    with patch("PyQt6.QtWidgets.QFileDialog.getExistingDirectory", return_value="/tmp/data"):
        with patch.object(controller_widget, "start_data_loading") as mock_start:
            controller_widget.load_data_folder()
            mock_start.assert_called_with("/tmp/data")


def test_controller_populate_trees(controller_widget):
    """Test populate_trees."""
    # Mock data
    dev = MagicMock()
    dev.name = "TV"
    btn = MagicMock()
    btn.name = "Power"
    btn.code.protocol = "nec"
    dev.buttons = [btn]
    controller_widget.device_ctrl.devices = [dev]

    auto = MagicMock()
    auto.name = "Movie Time"
    auto.triggers = []
    controller_widget.device_ctrl.automations = [auto]

    controller_widget.populate_trees()

    assert controller_widget.dev_tree.topLevelItemCount() == 1
    assert controller_widget.auto_tree.topLevelItemCount() == 1


@pytest.fixture
def main_window(app):
    """Pytest fixture for the MainWindow."""
    with (
        patch("tools.simulator.simulator_gui.SimulatorEngine"),
        patch("tools.simulator.simulator_gui.DeviceController"),
        patch("tools.simulator.simulator_gui.CoreMqttClient"),
        patch("tools.simulator.simulator_gui.QTimer"),
    ):
        window = MainWindow()
        window.logs = MagicMock()
        return window


def test_main_window_toggle_connection_connect(main_window, qtbot):
    """Test the toggle_connection method for connecting."""
    main_window.engine.main_mqtt_client = None
    qtbot.mouseClick(main_window.conn_btn, Qt.MouseButton.LeftButton)
    main_window.engine.set_main_client.assert_called()
    assert main_window.conn_btn.text() == "Connecting..."


def test_main_window_toggle_connection_disconnect(main_window, qtbot):
    """Test the toggle_connection method for disconnecting."""
    main_window.engine.main_mqtt_client = MagicMock()
    main_window.engine.main_mqtt_client.is_connected.return_value = True
    qtbot.mouseClick(main_window.conn_btn, Qt.MouseButton.LeftButton)
    assert main_window.conn_btn.text() == "Disconnecting..."


def test_tools_widget(app, qtbot):
    """Test the Tools widget."""
    engine = MagicMock(spec=SimulatorEngine)
    engine.main_mqtt_client = MagicMock()
    widget = Tools(engine)

    widget.handle_message("test/topic", "payload", True)
    assert widget.topic_list.topLevelItemCount() == 1

    widget.topic_input.setText("manual/topic")
    qtbot.mouseClick(widget.findChild(QWidget, "clear_manual_btn"), Qt.MouseButton.LeftButton)
    engine.main_mqtt_client.publish.assert_called_with("manual/topic", "", retain=True)

    item = widget.topic_list.topLevelItem(0)
    item.setSelected(True)
    qtbot.mouseClick(widget.findChild(QWidget, "clear_selected_btn"), Qt.MouseButton.LeftButton)
    engine.main_mqtt_client.publish.assert_called_with("test/topic", "", retain=True)

    qtbot.mouseClick(widget.findChild(QWidget, "refresh_btn"), Qt.MouseButton.LeftButton)
    engine.main_mqtt_client.client.unsubscribe.assert_called_with("#")
    engine.main_mqtt_client.client.subscribe.assert_called_with("#")


def test_main_window_handle_message(main_window):
    """Test the handle_mqtt_message method."""
    main_window.handle_mqtt_message("ir2mqtt/bridge/b1/command", "payload", False)
    main_window.logs.add_log.assert_called_with("Backend -> Bridge", "ir2mqtt/bridge/b1/command", "payload", retained=False)


def test_main_window_update_conn_ui(main_window):
    """Test the update_conn_ui method."""
    main_window.update_conn_ui(True, "")
    assert main_window.status_lbl.text() == "Connected"

    main_window.update_conn_ui(False, "")
    assert main_window.status_lbl.text() == "Disconnected"


def test_tools_clear_manual(app):
    """Test Tools clear manual."""
    engine = MagicMock(spec=SimulatorEngine)
    engine.main_mqtt_client = MagicMock()
    widget = Tools(engine)

    widget.topic_input.setText("test/topic")
    widget.clear_manual()

    engine.main_mqtt_client.publish.assert_called_with("test/topic", "", retain=True)
