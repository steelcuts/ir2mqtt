import os
import re
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add project root to the Python path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools", "simulator"))


from tools.simulator.engine import BridgeState  # noqa: E402
from tools.simulator.simulator_cli import SimulatorCLI  # noqa: E402
from tools.simulator.simulator_cli import main as cli_main  # noqa: E402
from tools.simulator.simulator_core import ALL_PROTOCOLS, CoreMqttClient, DeviceController, SimulatorEngine, sanitize_topic  # noqa: E402


def strip_ansi_codes(text):
    """Remove ANSI escape codes from a string."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def cli():
    """Pytest fixture for the SimulatorCLI."""
    engine = MagicMock(spec=SimulatorEngine)
    controller = MagicMock(spec=DeviceController)
    mqtt = MagicMock(spec=CoreMqttClient)
    return SimulatorCLI(engine, controller, mqtt)


def test_handle_list(cli, capsys):
    """Test the _handle_list method."""
    cli.engine.bridges = [BridgeState(id="bridge1", ip="1.2.3.4", name="Bridge 1", online=True)]
    dev_mock = MagicMock()
    dev_mock.name = "dev1"
    cli.controller.devices = [dev_mock]
    auto_mock = MagicMock()
    auto_mock.name = "auto1"
    cli.controller.automations = [auto_mock]

    cli._handle_list(None)

    captured = capsys.readouterr()
    assert "Bridges (1):" in captured.out
    # Now the output includes bridge_type and RX/TX capabilities
    assert "bridge1" in captured.out
    assert "Bridge 1" in captured.out
    assert "Online" in captured.out
    assert "RX:" in captured.out
    assert "TX:" in captured.out
    assert "Devices (1):" in captured.out
    assert "- dev1" in captured.out
    assert "Automations (1):" in captured.out
    assert "- auto1" in captured.out


def test_handle_spawn(cli, capsys):
    """Test the _handle_spawn method."""
    cli._handle_spawn(["spawn", "2"])
    cli.engine.spawn_bridges.assert_called_once_with(2)
    captured = capsys.readouterr()
    assert "2 MQTT bridge(s) spawned." in captured.out

    cli._handle_spawn(["spawn"])
    cli.engine.spawn_bridges.assert_called_with(1)

    cli._handle_spawn(["spawn", "serial", "3"])
    assert cli.engine.spawn_serial_bridge.call_count == 3
    captured = capsys.readouterr()
    assert "3 SERIAL bridge(s) spawned." in captured.out


def test_handle_delete(cli, capsys):
    """Test the _handle_delete method."""
    # Mock get_bridge_by_id to return True for "bridge1"
    cli.engine.get_bridge_by_id.side_effect = lambda bid: BridgeState(id=bid, ip="1.2.3.4", name=bid) if bid == "bridge1" else None

    cli._handle_delete(["delete", "bridge1"])
    cli.engine.delete_bridge.assert_called_once_with("bridge1")
    captured = capsys.readouterr()
    assert "Bridge bridge1 deleted." in captured.out

    # Test delete by index
    cli.engine.bridges = [BridgeState(id="bridge2", ip="1.2.3.4", name="Bridge 2")]
    cli._handle_delete(["delete", "1"])
    cli.engine.delete_bridge.assert_called_with("bridge2")

    cli._handle_delete(["delete"])
    captured = capsys.readouterr()
    assert "Usage: delete <bridge_id_or_index|all>" in captured.out


def test_handle_delete_all(cli, capsys):
    """Test the _handle_delete method with 'all'."""
    cli.engine.delete_all_bridges = MagicMock()

    cli._handle_delete(["delete", "all"])

    cli.engine.delete_all_bridges.assert_called_once()
    captured = capsys.readouterr()
    assert "All bridges deleted." in captured.out


def test_handle_protocols(cli, capsys):
    """Test the _handle_protocols method."""
    # Mock bridge
    bridge_mock = MagicMock(spec=BridgeState)
    bridge_mock.enabled_protocols = ["nec"]
    cli.engine.get_bridge_by_id.side_effect = lambda bid: bridge_mock if bid == "bridge1" else None

    # 1. List protocols
    cli._handle_protocols(["protocols", "bridge1", "list"])
    captured = capsys.readouterr()
    assert "Protocols for bridge1:" in captured.out
    assert "[x] nec" in captured.out

    # 2. Enable protocol
    cli.engine.update_protocols = MagicMock()
    # We use a real protocol from ALL_PROTOCOLS to pass validation
    proto_to_add = [p for p in ALL_PROTOCOLS if p != "nec"][0]
    cli._handle_protocols(["protocols", "bridge1", "enable", proto_to_add])

    # Verify update_protocols was called. Note: set order is not guaranteed.
    args, _ = cli.engine.update_protocols.call_args
    assert args[0] == "bridge1"
    assert set(args[1]) == {"nec", proto_to_add}
    captured = capsys.readouterr()
    assert f"Protocol '{proto_to_add}' enabled for bridge1." in captured.out

    # 3. Disable protocol
    cli.engine.update_protocols.reset_mock()
    cli._handle_protocols(["protocols", "bridge1", "disable", "nec"])
    args, _ = cli.engine.update_protocols.call_args
    assert args[0] == "bridge1"
    assert set(args[1]) == set()  # Should be empty now
    capsys.readouterr()  # Clear buffer

    # 4. Error cases
    cli._handle_protocols(["protocols", "invalid_bridge"])
    assert "Error: Bridge 'invalid_bridge' not found." in capsys.readouterr().out

    cli._handle_protocols(["protocols", "bridge1", "enable", "invalid_proto"])
    assert "Error: Unknown protocol 'invalid_proto'" in capsys.readouterr().out


def test_handle_simpress(cli, capsys):
    """Test the _handle_simpress method."""
    mock_code = MagicMock()
    mock_code.model_dump.return_value = {"protocol": "nec", "address": "0x10", "command": "0x20"}
    btn_mock = MagicMock(code=mock_code)
    cli.controller.find_device_and_button.return_value = (MagicMock(), btn_mock)

    cli._handle_simpress(["simpress", "bridge1", "dev1", "btn1"])

    cli.engine.inject_signal.assert_called_once_with("bridge1", {"protocol": "nec", "address": "0x10", "command": "0x20"})
    captured = capsys.readouterr()
    assert "Simulating press on 'dev1 -> btn1' via bridge bridge1" in captured.out


def test_handle_simpress_no_code(cli, capsys):
    """Test the _handle_simpress method when the button has no code."""
    btn_mock = MagicMock(code=None)
    cli.controller.find_device_and_button.return_value = (MagicMock(), btn_mock)

    cli._handle_simpress(["simpress", "bridge1", "dev1", "btn1"])

    captured = capsys.readouterr()
    assert "Error: Button 'btn1' in device 'dev1' not found or has no code." in captured.out


def test_handle_command_hacmd(cli, capsys):
    """Test the _handle_command method with 'hacmd'."""
    dev_mock = MagicMock(id="dev1_id")
    btn_mock = MagicMock(id="btn1_id")
    cli.controller.find_device_and_button.return_value = (dev_mock, btn_mock)

    cli._handle_command(["hacmd", "dev1", "btn1"])

    cli.mqtt.publish.assert_called_once_with("ir2mqtt/cmd/dev1_id/btn1_id", "PRESS")
    captured = capsys.readouterr()
    assert "MQTT command sent to: ir2mqtt/cmd/dev1_id/btn1_id" in captured.out


def test_handle_command_sacmd(cli, capsys):
    """Test the _handle_command method with 'sacmd'."""
    dev_mock = MagicMock()
    dev_mock.name = "My Device"
    btn_mock = MagicMock()
    btn_mock.name = "My Button"
    cli.controller.find_device_and_button.return_value = (dev_mock, btn_mock)

    cli._handle_command(["sacmd", "My Device", "My Button"])

    sanitized_dev_name = sanitize_topic(dev_mock.name)
    sanitized_btn_name = sanitize_topic(btn_mock.name)

    cli.mqtt.publish.assert_called_once_with(f"ir2mqtt/devices/{sanitized_dev_name}/{sanitized_btn_name}/in", "PRESS")
    captured = capsys.readouterr()
    assert f"MQTT command sent to: ir2mqtt/devices/{sanitized_dev_name}/{sanitized_btn_name}/in" in captured.out


def test_handle_trigger(cli, capsys):
    """Test the _handle_trigger method."""
    auto_mock = MagicMock()
    auto_mock.name = "My Automation"
    cli.controller.find_automation.return_value = auto_mock

    cli._handle_trigger(["trigger", "My Automation"])

    sanitized_auto_name = sanitize_topic(auto_mock.name)
    cli.mqtt.publish.assert_called_once_with(f"ir2mqtt/automations/{sanitized_auto_name}/trigger", "PRESS")
    captured = capsys.readouterr()
    assert "Automation 'My Automation' triggered." in captured.out


def test_handle_trigger_not_found(cli, capsys):
    """Test the _handle_trigger method when the automation is not found."""
    cli.controller.find_automation.return_value = None

    cli._handle_trigger(["trigger", "My Automation"])

    captured = capsys.readouterr()
    assert "Error: Automation not found." in captured.out


def test_console_logger(cli, capsys):
    """Test the _console_logger method."""
    cli.show_logs = True
    cli._console_logger("TEST", "Test message", "INFO")
    captured = capsys.readouterr()
    assert "[INFO] [TEST] Test message" in strip_ansi_codes(captured.out)

    cli.show_logs = False
    cli._console_logger("TEST", "Another message", "INFO")
    captured = capsys.readouterr()
    assert "Another message" not in captured.out


def test_on_main_client_connection_change(cli, capsys):
    """Test the on_main_client_connection_change method."""
    cli.show_logs = True
    cli.on_main_client_connection_change(True, None)
    captured = capsys.readouterr()
    assert "Main client successfully connected" in strip_ansi_codes(captured.out)

    cli.on_main_client_connection_change(False, "Error")
    captured = capsys.readouterr()
    assert "Main client disconnected. Error" in strip_ansi_codes(captured.out)


@patch("tools.simulator.simulator_cli.SimulatorCLI")
@patch("tools.simulator.simulator_cli.SimulatorEngine")
@patch("tools.simulator.simulator_cli.DeviceController")
@patch("tools.simulator.simulator_cli.CoreMqttClient")
@patch("tools.simulator.simulator_cli.argparse.ArgumentParser")
@patch("asyncio.run")
def test_main(mock_asyncio_run, mock_argparse, mock_mqtt, mock_device_controller, mock_engine, mock_cli):
    """Test the main function."""

    mock_parser = MagicMock()
    mock_parser.parse_args.return_value = MagicMock(broker="localhost", port=1883, data="/data")
    mock_argparse.return_value = mock_parser

    # This mocks the cli.run() call to prevent an infinite loop
    mock_cli.return_value.run = MagicMock()

    cli_main()

    mock_engine.assert_called_once()
    mock_device_controller.assert_called_once()
    mock_mqtt.assert_called_once()
    mock_cli.assert_called_once()
    mock_cli.return_value.run.assert_called_once()


def test_run(cli, capsys):
    """Test the run method."""
    with patch("builtins.input", side_effect=["help", "unknown", "exit"]):
        cli.run()

    captured = capsys.readouterr()
    assert "--- CLI COMMANDS ---" in captured.out
    assert "Unknown command: unknown" in captured.out
