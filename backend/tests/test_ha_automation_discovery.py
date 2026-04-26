from unittest.mock import ANY, MagicMock

import pytest

from backend.ha_automation_discovery import (
    get_automations_device,
    publish_automation_button,
    publish_automation_ha_event_triggers,
    publish_automation_running_sensor,
    send_ha_discovery_for_automation,
    unpublish_automation_button,
    unpublish_automation_entities,
    unpublish_automation_ha_event_triggers,
    unpublish_automation_running_sensor,
)
from backend.models import IRAutomation, IRAutomationAction


@pytest.fixture
def mock_mqtt_manager():
    return MagicMock()


def test_get_automations_device():
    dev = get_automations_device()
    assert dev["identifiers"] == ["ir2mqtt_automations_device"]
    assert dev["name"] == "ir2mqtt Automations"


def test_publish_automation_button(mock_mqtt_manager):
    auto = IRAutomation(id="auto1", name="Test Auto")
    dev_info = {"identifiers": ["test"]}

    publish_automation_button(auto, dev_info, mock_mqtt_manager)

    config_topic = "homeassistant/button/ir2mqtt_auto/auto1/config"
    mock_mqtt_manager.publish.assert_called_with(config_topic, ANY, retain=True)
    mock_mqtt_manager.subscribe.assert_called_with("ir2mqtt/automation/auto1/trigger")


def test_unpublish_automation_button(mock_mqtt_manager):
    auto = IRAutomation(id="auto1", name="Test Auto")

    unpublish_automation_button(auto, mock_mqtt_manager)

    config_topic = "homeassistant/button/ir2mqtt_auto/auto1/config"
    mock_mqtt_manager.publish.assert_called_with(config_topic, "", retain=True)
    mock_mqtt_manager.unsubscribe.assert_called_with("ir2mqtt/automation/auto1/trigger")


def test_publish_automation_running_sensor(mock_mqtt_manager):
    auto = IRAutomation(id="auto1", name="Test Auto")
    dev_info = {"identifiers": ["test"]}

    publish_automation_running_sensor(auto, dev_info, mock_mqtt_manager)

    config_topic = "homeassistant/binary_sensor/ir2mqtt_auto/auto1_running/config"
    mock_mqtt_manager.publish.assert_called_with(config_topic, ANY, retain=True)


def test_unpublish_automation_running_sensor(mock_mqtt_manager):
    auto = IRAutomation(id="auto1", name="Test Auto")

    unpublish_automation_running_sensor(auto, mock_mqtt_manager)

    config_topic = "homeassistant/binary_sensor/ir2mqtt_auto/auto1_running/config"
    mock_mqtt_manager.publish.assert_called_with(config_topic, "", retain=True)


def test_publish_automation_ha_event_triggers(mock_mqtt_manager):
    auto = IRAutomation(
        id="auto1",
        name="Test Auto",
        actions=[
            IRAutomationAction(type="event", event_name="Event A"),
            IRAutomationAction(type="event", event_name="Event B"),
            IRAutomationAction(type="delay", delay_ms=100),
        ],
    )
    dev_info = {"identifiers": ["test"]}

    publish_automation_ha_event_triggers(auto, dev_info, mock_mqtt_manager)

    safe_name_a = "event_a"
    config_topic_a = f"homeassistant/event/ir2mqtt_auto_event/auto1_{safe_name_a}/config"

    calls = mock_mqtt_manager.publish.call_args_list
    topics = [c[0][0] for c in calls]

    assert config_topic_a in topics


def test_unpublish_automation_ha_event_triggers(mock_mqtt_manager):
    auto = IRAutomation(
        id="auto1",
        name="Test Auto",
        actions=[IRAutomationAction(type="event", event_name="Event A")],
    )

    unpublish_automation_ha_event_triggers(auto, mock_mqtt_manager)

    safe_name = "event_a"
    event_topic = f"homeassistant/event/ir2mqtt_auto_event/auto1_{safe_name}/config"

    mock_mqtt_manager.publish.assert_any_call(event_topic, "", retain=True)


def test_send_ha_discovery_for_automation(mock_mqtt_manager):
    auto = IRAutomation(id="auto1", name="Test Auto", ha_expose_button=True)
    send_ha_discovery_for_automation(auto, mock_mqtt_manager)
    assert mock_mqtt_manager.publish.call_count >= 2


def test_unpublish_automation_entities(mock_mqtt_manager):
    auto = IRAutomation(id="auto1", name="Test Auto")
    unpublish_automation_entities(auto, mock_mqtt_manager)
    mock_mqtt_manager.publish.assert_any_call("homeassistant/button/ir2mqtt_auto/auto1/config", "", retain=True)
