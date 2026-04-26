#!/usr/bin/env python3
"""Quick test script to verify Serial Bridge simulation features."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.simulator.engine import BridgeConfig, BridgeState, ReceiverConfig, SimulatorEngine, TransmitterConfig


def test_bridge_config_mqtt():
    """Test BridgeConfig for MQTT bridges."""
    cfg = BridgeConfig(bid="test-1", bridge_type="mqtt", ip="192.168.1.100", protocols=["nec"])
    assert cfg.bid == "test-1"
    assert cfg.bridge_type == "mqtt"
    assert cfg.ip == "192.168.1.100"
    assert cfg.port is None
    print("✅ BridgeConfig for MQTT bridges works")


def test_bridge_config_serial():
    """Test BridgeConfig for Serial bridges."""
    cfg = BridgeConfig(bid="test-2", bridge_type="serial", port="/dev/ttyUSB0", baudrate=115200, protocols=["nec"])
    assert cfg.bid == "test-2"
    assert cfg.bridge_type == "serial"
    assert cfg.port == "/dev/ttyUSB0"
    assert cfg.baudrate == 115200
    assert cfg.ip is None
    print("✅ BridgeConfig for Serial bridges works")


def test_bridge_state():
    """Test BridgeState model."""
    receivers = [ReceiverConfig(id="ir_rx_main")]
    transmitters = [TransmitterConfig(id="ir_tx_main"), TransmitterConfig(id="ir_tx_2")]
    state = BridgeState(id="bridge-1", name="Test Bridge", receivers=receivers, transmitters=transmitters)
    assert state.id == "bridge-1"
    assert state.bridge_type == "mqtt"  # default
    assert state.rx == 1
    assert state.tx == 2
    assert state.online is False  # default
    print("✅ BridgeState model works with proper defaults")


def test_simulator_mqtt_bridge():
    """Test spawning MQTT bridges in simulator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, "sim_config.json")

        def dummy_log(src, msg, level):
            pass

        def dummy_update():
            pass

        engine = SimulatorEngine("localhost", 1883, dummy_log, dummy_update, config_file)

        # Spawn an MQTT bridge
        engine.spawn_bridges(1)

        # Verify bridge was created
        assert len(engine.bridges) == 1
        bridge = engine.bridges[0]
        assert bridge.bridge_type == "mqtt"
        assert bridge.ip is not None
        assert bridge.rx >= 1
        assert bridge.tx >= 1
        print(f"✅ Created MQTT bridge: {bridge.id} at {bridge.ip}")

        # Verify config was saved
        assert os.path.exists(config_file)
        with open(config_file) as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["bridge_type"] == "mqtt"
            print(f"✅ Config saved with bridge_type: {data[0]['bridge_type']}")


def test_simulator_serial_bridge():
    """Test spawning Serial bridges in simulator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, "sim_config.json")

        def dummy_log(src, msg, level):
            print(f"[{level}] {msg}")

        def dummy_update():
            pass

        engine = SimulatorEngine("localhost", 1883, dummy_log, dummy_update, config_file)

        # Create a serial bridge
        bid = engine.spawn_serial_bridge("/dev/ttyUSB0", 115200)

        # Verify bridge was created
        assert len(engine.bridges) == 1
        bridge = engine.get_bridge_by_id(bid)
        assert bridge is not None
        assert bridge.bridge_type == "serial"
        assert bridge.port is not None
        assert bridge.ip is None
        print(f"✅ Created Serial bridge: {bid} on port {bridge.port}")

        # Verify config was saved
        assert os.path.exists(config_file)
        with open(config_file) as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["bridge_type"] == "serial"
            assert data[0]["port"] == "/dev/ttyUSB0"
            assert data[0]["baudrate"] == 115200
            print(f"✅ Config saved with bridge_type: {data[0]['bridge_type']}, port: {data[0]['port']}")


def test_config_save_load():
    """Test saving and loading mixed bridge configs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = os.path.join(tmpdir, "sim_config.json")

        def dummy_log(src, msg, level):
            pass

        def dummy_update():
            pass

        # Create engine and add bridges
        engine = SimulatorEngine("localhost", 1883, dummy_log, dummy_update, config_file)

        engine.spawn_bridges(1)  # MQTT
        engine.spawn_serial_bridge("/dev/ttyUSB0")  # Serial

        # Verify config
        configs = engine.simulated_configs
        assert len(configs) == 2
        mqtt_cfg = next(c for c in configs if c.bridge_type == "mqtt")
        serial_cfg = next(c for c in configs if c.bridge_type == "serial")
        assert mqtt_cfg.ip is not None
        assert serial_cfg.port == "/dev/ttyUSB0"
        print("✅ Created mixed bridges (1 MQTT, 1 Serial)")

        # Load into new engine
        engine2 = SimulatorEngine("localhost", 1883, dummy_log, dummy_update, config_file)

        # Verify configs were loaded
        assert len(engine2.simulated_configs) == 2, f"Expected 2 configs, got {len(engine2.simulated_configs)}"
        mqtt_cfg2 = next(c for c in engine2.simulated_configs if c.bridge_type == "mqtt")
        serial_cfg2 = next(c for c in engine2.simulated_configs if c.bridge_type == "serial")
        assert mqtt_cfg2.ip == mqtt_cfg.ip
        assert serial_cfg2.port == "/dev/ttyUSB0"
        print("✅ Mixed bridge configs saved and loaded correctly")


if __name__ == "__main__":
    test_bridge_config_mqtt()
    test_bridge_config_serial()
    test_bridge_state()
    test_simulator_mqtt_bridge()
    test_simulator_serial_bridge()
    test_config_save_load()
    print("\n✅ All Serial Bridge simulator tests passed!")
