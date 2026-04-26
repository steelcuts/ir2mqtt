import json
import logging

from .models import IRAutomation
from .mqtt import MQTTManager
from .utils import sanitize_topic_part

logger = logging.getLogger("ir2mqtt")


def get_automations_device() -> dict:
    """Returns the device info for the virtual Automations device."""
    return {
        "identifiers": ["ir2mqtt_automations_device"],
        "name": "ir2mqtt Automations",
        "model": "Software Automations",
        "manufacturer": "ir2mqtt",
    }


def publish_automation_button(automation: IRAutomation, dev_info: dict, mqtt_manager: MQTTManager):
    """Publishes the discovery config for an automation's trigger button."""
    safe_auto_id = automation.id
    config_topic = f"homeassistant/button/ir2mqtt_auto/{safe_auto_id}/config"
    command_topic = f"ir2mqtt/automation/{safe_auto_id}/trigger"

    payload = {
        "name": automation.name,
        "unique_id": f"ir2mqtt_auto_button_{safe_auto_id}",
        "command_topic": command_topic,
        "payload_press": "PRESS",
        "device": dev_info,
        "icon": "mdi:play-circle-outline",
        "entity_category": "config",
    }
    mqtt_manager.publish(config_topic, json.dumps(payload), retain=True)
    mqtt_manager.subscribe(command_topic)


def unpublish_automation_button(automation: IRAutomation, mqtt_manager: MQTTManager):
    """Removes the discovery config for an automation's trigger button."""
    safe_auto_id = automation.id
    config_topic = f"homeassistant/button/ir2mqtt_auto/{safe_auto_id}/config"
    command_topic = f"ir2mqtt/automation/{safe_auto_id}/trigger"
    mqtt_manager.unsubscribe(command_topic)
    mqtt_manager.publish(config_topic, "", retain=True)


def publish_automation_running_sensor(automation: IRAutomation, dev_info: dict, mqtt_manager: MQTTManager):
    """Publishes a binary sensor that is ON while the automation is running."""
    safe_auto_id = automation.id
    config_topic = f"homeassistant/binary_sensor/ir2mqtt_auto/{safe_auto_id}_running/config"
    state_topic = f"ir2mqtt/automation/{safe_auto_id}/state"

    payload = {
        "name": f"{automation.name} Running",
        "unique_id": f"ir2mqtt_auto_running_{safe_auto_id}",
        "state_topic": state_topic,
        "payload_on": "ON",
        "payload_off": "OFF",
        "device": dev_info,
        "icon": "mdi:progress-clock",
        "entity_category": "diagnostic",
    }
    mqtt_manager.publish(config_topic, json.dumps(payload), retain=True)


def unpublish_automation_running_sensor(automation: IRAutomation, mqtt_manager: MQTTManager):
    safe_auto_id = automation.id
    config_topic = f"homeassistant/binary_sensor/ir2mqtt_auto/{safe_auto_id}_running/config"
    mqtt_manager.publish(config_topic, "", retain=True)


def publish_automation_ha_event_triggers(automation: IRAutomation, dev_info: dict, mqtt_manager: MQTTManager):
    """Publishes discovery for all unique HA Event actions in an automation."""
    safe_auto_id = automation.id
    filtered_actions = [action.event_name for action in automation.actions if action.type == "event" and action.event_name]
    event_names = sorted(list(set(filtered_actions)))

    # Group by safe name to handle case/space collisions
    grouped_events = {}
    for name in event_names:
        safe = sanitize_topic_part(name)
        if safe not in grouped_events:
            grouped_events[safe] = []
        grouped_events[safe].append(name)

    for safe_event_name, types in grouped_events.items():
        display_name = types[0]

        config_topic = f"homeassistant/event/ir2mqtt_auto_event/{safe_auto_id}_{safe_event_name}/config"
        base_topic = f"ir2mqtt/automation_event/{safe_auto_id}/{safe_event_name}"

        payload = {
            "name": f"{display_name}",
            "unique_id": f"ir2mqtt_auto_event_{safe_auto_id}_{safe_event_name}",
            "state_topic": f"{base_topic}/state",
            "event_types": ["press"],
            "json_attributes_topic": f"{base_topic}/attributes",
            "device": dev_info,
            "device_class": "button",
            "icon": "mdi:lightning-bolt",
            "entity_category": "diagnostic",
        }
        mqtt_manager.publish(config_topic, json.dumps(payload), retain=True)


def unpublish_automation_ha_event_triggers(automation: IRAutomation, mqtt_manager: MQTTManager):
    """Removes discovery for all unique HA Event actions in an automation."""
    safe_auto_id = automation.id
    filtered_actions = [action.event_name for action in automation.actions if action.type == "event" and action.event_name]
    event_names = sorted(list(set(filtered_actions)))

    for event_name in event_names:
        safe_event_name = sanitize_topic_part(event_name)
        config_topic = f"homeassistant/event/ir2mqtt_auto_event/{safe_auto_id}_{safe_event_name}/config"
        mqtt_manager.publish(config_topic, "", retain=True)


def send_ha_discovery_for_automation(automation: IRAutomation, mqtt_manager: MQTTManager):
    """Main function to dispatch discovery for a single automation."""
    dev_info = get_automations_device()

    # Button
    if automation.ha_expose_button:
        publish_automation_button(automation, dev_info, mqtt_manager)
    else:
        unpublish_automation_button(automation, mqtt_manager)

    # Running Status Sensor
    publish_automation_running_sensor(automation, dev_info, mqtt_manager)

    # HA Event Triggers
    # Publish the current ones.
    publish_automation_ha_event_triggers(automation, dev_info, mqtt_manager)


def send_ha_discovery_for_all_automations(automations: list[IRAutomation], mqtt_manager: MQTTManager):
    logger.info("Sending Home Assistant discovery for all automations...")
    for auto in automations:
        send_ha_discovery_for_automation(auto, mqtt_manager)


def unpublish_automation_entities(automation: IRAutomation, mqtt_manager: MQTTManager):
    """Unpublishes all HA entities associated with a given automation."""
    logger.info("Unpublishing all HA entities for automation '%s'", automation.name)
    unpublish_automation_button(automation, mqtt_manager)
    unpublish_automation_running_sensor(automation, mqtt_manager)
    unpublish_automation_ha_event_triggers(automation, mqtt_manager)
