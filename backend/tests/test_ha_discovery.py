from unittest.mock import MagicMock

import pytest

from backend.ha_discovery import (
    send_ha_discovery_for_all,
    send_ha_discovery_for_device,
    send_ha_discovery_for_entities,
    send_ha_discovery_for_last_button_sensor,
    send_ha_discovery_for_triggers,
)
from backend.models import IRButton, IRDevice
from backend.state import StateManager


@pytest.fixture
def mock_mqtt_manager():
    return MagicMock()


@pytest.fixture
def mock_state_manager():
    return StateManager()


def test_send_ha_discovery_for_entities_input_and_output(mock_mqtt_manager):
    device = IRDevice(
        id="dev1",
        name="Test Device",
        buttons=[
            IRButton(
                id="btn1",
                name="Power",
                icon="power",
                is_input=True,
                is_output=True,
                is_event=True,
                input_mode="toggle",
            ),
            IRButton(id="btn2", name="Mute", is_input=False, is_output=False),
        ],
    )
    dev_info = {"name": "Test Device", "identifiers": ["ir2mqtt_dev1"]}

    send_ha_discovery_for_entities(device, dev_info, mock_mqtt_manager)

    # Assert btn1 is published as both binary_sensor and button.
    assert mock_mqtt_manager.publish.call_count == 4

    # Check binary_sensor config for btn1.
    config_topic_sensor = "homeassistant/binary_sensor/ir_dev1/btn1/config"
    mock_mqtt_manager.publish.assert_any_call(
        config_topic_sensor,
        '{"name": "Power", "unique_id": "ir2mqtt_dev1_btn1", "state_topic": "ir2mqtt/input/dev1/btn1/state", '
        '"device": {"name": "Test Device", "identifiers": ["ir2mqtt_dev1"]}, "payload_on": "ON", '
        '"payload_off": "OFF", "icon": "mdi:power"}',
        retain=True,
    )

    # Check button config for btn1.
    config_topic_btn = "homeassistant/button/ir_dev1/btn1/config"
    mock_mqtt_manager.publish.assert_any_call(
        config_topic_btn,
        '{"name": "Power", "unique_id": "ir2mqtt_dev1_btn1", "command_topic": "ir2mqtt/cmd/dev1/btn1", '
        '"payload_press": "PRESS", "device": {"name": "Test Device", "identifiers": ["ir2mqtt_dev1"]}, "icon": "mdi:power"}',
        retain=True,
    )

    # Assert btn2 is unpublished (empty payload).
    mock_mqtt_manager.publish.assert_any_call("homeassistant/binary_sensor/ir_dev1/btn2/config", "", retain=True)
    mock_mqtt_manager.publish.assert_any_call("homeassistant/button/ir_dev1/btn2/config", "", retain=True)

    # Assert subscribe is called for the command topic of the output button.
    mock_mqtt_manager.subscribe.assert_called_once_with("ir2mqtt/cmd/dev1/btn1")


def test_send_ha_discovery_for_last_button_sensor(mock_mqtt_manager):
    device = IRDevice(id="dev1", name="Test Device")
    dev_info = {"name": "Test Device", "identifiers": ["ir2mqtt_dev1"]}

    send_ha_discovery_for_last_button_sensor(device, dev_info, mock_mqtt_manager)

    config_topic = "homeassistant/sensor/ir_dev1/last_button/config"
    payload = (
        '{"name": "Last Button Pressed", "unique_id": "ir2mqtt_dev1_last_button", '
        '"state_topic": "ir2mqtt/status/dev1/last_button", '
        '"device": {"name": "Test Device", "identifiers": ["ir2mqtt_dev1"]}, "icon": "mdi:remote"}'
    )
    mock_mqtt_manager.publish.assert_called_once_with(config_topic, payload, retain=True)


def test_send_ha_discovery_for_triggers(mock_mqtt_manager):
    device = IRDevice(
        id="dev1",
        name="Test Device",
        buttons=[
            IRButton(id="btn1", name="Power", is_event=True),
            IRButton(id="btn2", name="Mute", is_event=False),
        ],
    )
    dev_info = {"name": "Test Device", "identifiers": ["ir2mqtt_dev1"]}

    send_ha_discovery_for_triggers(device, dev_info, mock_mqtt_manager)

    # Assert trigger is published for btn1.
    config_topic_trigger = "homeassistant/device_automation/ir_dev1/action_btn1/config"
    mock_mqtt_manager.publish.assert_any_call(
        config_topic_trigger,
        '{"automation_type": "trigger", "topic": "ir2mqtt/events/dev1", "type": "button_short_press", '
        '"subtype": "Power", "payload": "Power", "device": {"name": "Test Device", "identifiers": ["ir2mqtt_dev1"]}, '
        '"unique_id": "ir2mqtt_dev1_btn1_trigger"}',
        retain=True,
    )

    # Assert trigger is unpublished for btn2.
    mock_mqtt_manager.publish.assert_any_call("homeassistant/device_automation/ir_dev1/action_btn2/config", "", retain=True)


def test_send_ha_discovery_for_device(mock_mqtt_manager):
    device = IRDevice(
        id="dev1",
        name="Test Device",
        buttons=[
            IRButton(id="btn1", name="Power", is_input=True, is_output=True, is_event=True),
        ],
    )

    send_ha_discovery_for_device(device, mock_mqtt_manager)

    # Check that all discovery functions are called.
    assert mock_mqtt_manager.publish.call_count == 4


@pytest.mark.asyncio
async def test_send_ha_discovery_for_all(mock_state_manager, mock_mqtt_manager):
    devices = [
        IRDevice(
            id="dev1",
            name="Test Device 1",
            buttons=[IRButton(id="btn1", name="Power")],
        ),
        IRDevice(
            id="dev2",
            name="Test Device 2",
            buttons=[IRButton(id="btn2", name="Volume Up")],
        ),
    ]
    mock_state_manager.devices = devices

    await send_ha_discovery_for_all(mock_state_manager, mock_mqtt_manager)

    # 4 publish calls per device.
    assert mock_mqtt_manager.publish.call_count == 8
