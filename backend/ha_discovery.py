import json
import logging

from .models import IRDevice
from .mqtt import MQTTManager
from .state import StateManager

logger = logging.getLogger("ir2mqtt")


def send_ha_discovery_for_entities(device: IRDevice, dev_info: dict, mqtt_manager: MQTTManager):
    """Handles HA discovery for device entities (buttons, sensors)."""
    safe_dev_id = device.id

    for btn in device.buttons:
        # 1. Handle Input (Binary Sensor)
        config_topic_sensor = f"homeassistant/binary_sensor/ir_{safe_dev_id}/{btn.id}/config"
        if btn.is_input:
            state_topic = f"ir2mqtt/input/{safe_dev_id}/{btn.id}/state"
            payload = {
                "name": btn.name,
                "unique_id": f"ir2mqtt_{safe_dev_id}_{btn.id}",
                "state_topic": state_topic,
                "device": dev_info,
                "payload_on": "ON",
                "payload_off": "OFF",
            }
            if btn.icon:
                payload["icon"] = f"mdi:{btn.icon}"

            if getattr(btn, "input_mode", "momentary") in ["momentary", "timed"]:
                payload["off_delay"] = getattr(btn, "input_off_delay_s", 1)
            mqtt_manager.publish(config_topic_sensor, json.dumps(payload), retain=True)
        else:
            mqtt_manager.publish(config_topic_sensor, "", retain=True)

        # 2. Handle Output (Button)
        config_topic_btn = f"homeassistant/button/ir_{safe_dev_id}/{btn.id}/config"
        if btn.is_output:
            command_topic = f"ir2mqtt/cmd/{safe_dev_id}/{btn.id}"
            payload = {
                "name": btn.name,
                "unique_id": f"ir2mqtt_{safe_dev_id}_{btn.id}",
                "command_topic": command_topic,
                "payload_press": "PRESS",
                "device": dev_info,
            }
            if btn.icon:
                payload["icon"] = f"mdi:{btn.icon}"

            mqtt_manager.publish(config_topic_btn, json.dumps(payload), retain=True)
            mqtt_manager.subscribe(command_topic)
        else:
            mqtt_manager.publish(config_topic_btn, "", retain=True)


def send_ha_discovery_for_last_button_sensor(device: IRDevice, dev_info: dict, mqtt_manager: MQTTManager):
    """Creates a text sensor in HA that shows the name of the last received button."""
    safe_dev_id = device.id
    config_topic = f"homeassistant/sensor/ir_{safe_dev_id}/last_button/config"
    state_topic = f"ir2mqtt/status/{safe_dev_id}/last_button"

    payload = {
        "name": "Last Button Pressed",
        "unique_id": f"ir2mqtt_{safe_dev_id}_last_button",
        "state_topic": state_topic,
        "device": dev_info,
        "icon": "mdi:remote",
    }
    mqtt_manager.publish(config_topic, json.dumps(payload), retain=True)


def send_ha_discovery_for_triggers(device: IRDevice, dev_info: dict, mqtt_manager: MQTTManager):
    """Registers device triggers for every button."""
    safe_dev_id = device.id
    topic = f"ir2mqtt/events/{safe_dev_id}"

    for btn in device.buttons:
        config_topic = f"homeassistant/device_automation/ir_{safe_dev_id}/action_{btn.id}/config"

        if btn.is_event:
            payload = {
                "automation_type": "trigger",
                "topic": topic,
                "type": "button_short_press",
                "subtype": btn.name,
                "payload": btn.name,
                "device": dev_info,
                "unique_id": f"ir2mqtt_{safe_dev_id}_{btn.id}_trigger",
            }
            mqtt_manager.publish(config_topic, json.dumps(payload), retain=True)
        else:
            mqtt_manager.publish(config_topic, "", retain=True)


def send_ha_discovery_for_device(device: IRDevice, mqtt_manager: MQTTManager):
    """Dispatches discovery to the correct function based on device_type."""
    safe_dev_id = device.id
    dev_info = {
        "identifiers": [f"ir2mqtt_{safe_dev_id}"],
        "name": device.name,
        "model": "IR Gateway Virtual Device",
        "manufacturer": "IR2MQTT",
    }

    send_ha_discovery_for_entities(device, dev_info, mqtt_manager)

    # Always add the 'Last Button' sensor
    send_ha_discovery_for_last_button_sensor(device, dev_info, mqtt_manager)
    # Always add device triggers
    send_ha_discovery_for_triggers(device, dev_info, mqtt_manager)


async def send_ha_discovery_for_all(state_manager: StateManager, mqtt_manager: MQTTManager):
    logger.info("Sending Home Assistant discovery for all devices...")
    for dev in state_manager.devices:
        send_ha_discovery_for_device(dev, mqtt_manager)
