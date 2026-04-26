import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod

from .ha_automation_discovery import (
    send_ha_discovery_for_automation,
    unpublish_automation_entities,
)
from .ha_discovery import send_ha_discovery_for_all, send_ha_discovery_for_device
from .models import IRAutomation, IRButton, IRDevice
from .utils import sanitize_topic_part

logger = logging.getLogger("ir2mqtt")


class BaseIntegration(ABC):
    def __init__(self, state_manager, settings=None):
        self.state_manager = state_manager
        self.settings = settings

    @abstractmethod
    async def on_mqtt_connect(self, mqtt_manager):
        pass

    @abstractmethod
    async def on_device_updated(self, device: IRDevice, mqtt_manager):
        pass

    @abstractmethod
    async def on_device_deleted(self, device: IRDevice, mqtt_manager):
        pass

    @abstractmethod
    async def on_automation_updated(self, automation: IRAutomation, mqtt_manager):
        pass

    @abstractmethod
    async def on_automation_deleted(self, automation: IRAutomation, mqtt_manager):
        pass

    @abstractmethod
    def get_subscribe_topics(self) -> list[str]:
        pass

    @abstractmethod
    def handle_message(self, topic: str, payload: str, mqtt_manager) -> bool:
        pass

    @abstractmethod
    def publish_button_event(self, device: IRDevice, button: IRButton, mqtt_manager):
        pass

    @abstractmethod
    def publish_input_state(self, device: IRDevice, button: IRButton, state: str, mqtt_manager):
        pass

    @abstractmethod
    def publish_automation_event(self, automation: IRAutomation, event_name: str, run_id: str, mqtt_manager):
        pass

    @abstractmethod
    def publish_automation_state(self, automation: IRAutomation, state: str, mqtt_manager):
        pass

    @abstractmethod
    async def clear_all(self, mqtt_manager):
        pass

    def _trigger_button(self, device, btn, mqtt_manager):
        targets = getattr(device, "target_bridges", [])
        code = btn.code.model_dump(exclude_none=True)
        if mqtt_manager.loop:
            if targets:
                for target in targets:
                    asyncio.run_coroutine_threadsafe(
                        mqtt_manager.send_ir_code(code, target=target),
                        mqtt_manager.loop,
                    )
            else:
                asyncio.run_coroutine_threadsafe(
                    mqtt_manager.send_ir_code(code, target="broadcast"),
                    mqtt_manager.loop,
                )


class HomeAssistantIntegration(BaseIntegration):
    NAME = "home_assistant"

    async def on_mqtt_connect(self, mqtt_manager):
        logger.info("[HA Integration] MQTT connected, sending full discovery.")
        await send_ha_discovery_for_all(self.state_manager, mqtt_manager)

    async def on_device_updated(self, device: IRDevice, mqtt_manager):
        logger.info("[HA Integration] Device updated: '%s'. Sending discovery.", device.name)
        send_ha_discovery_for_device(device, mqtt_manager)

    async def on_device_deleted(self, device: IRDevice, mqtt_manager):
        logger.info("[HA Integration] Device deleted: '%s'. Unpublishing entities.", device.name)
        # Last button sensor
        mqtt_manager.publish(f"homeassistant/sensor/ir_{device.id}/last_button/config", "", retain=True)
        # Buttons, binary sensors, and device automations (actions/triggers)
        for btn in device.buttons:
            mqtt_manager.publish(f"homeassistant/button/ir_{device.id}/{btn.id}/config", "", retain=True)
            mqtt_manager.publish(
                f"homeassistant/binary_sensor/ir_{device.id}/{btn.id}/config",
                "",
                retain=True,
            )
            # Deprecated device triggers/actions
            mqtt_manager.publish(
                f"homeassistant/device_automation/ir_{device.id}/action_{btn.id}/config",
                "",
                retain=True,
            )
        logger.debug("[HA Integration] Unpublishing for device %s complete.", device.id)

    async def on_automation_updated(self, automation: IRAutomation, mqtt_manager):
        logger.info(
            "[HA Integration] Automation updated: '%s'. Sending discovery.",
            automation.name,
        )
        send_ha_discovery_for_automation(automation, mqtt_manager)

    async def on_automation_deleted(self, automation: IRAutomation, mqtt_manager):
        logger.info(
            "[HA Integration] Automation deleted: '%s'. Unpublishing entities.",
            automation.name,
        )
        unpublish_automation_entities(automation, mqtt_manager)

    def get_subscribe_topics(self) -> list[str]:
        topics = []
        for dev in self.state_manager.devices:
            for btn in dev.buttons:
                # Corresponds to the button entity's command topic
                topics.append(f"ir2mqtt/cmd/{dev.id}/{btn.id}")
        # For HA-triggered automations
        topics.append("ir2mqtt/automation/+/trigger")
        logger.debug("[HA Integration] Subscribing to %d topics.", len(topics))
        return topics

    def handle_message(self, topic: str, payload: str, mqtt_manager) -> bool:
        parts = topic.split("/")
        # Handle command from a Home Assistant button entity
        if len(parts) == 4 and parts[0] == "ir2mqtt" and parts[1] == "cmd":
            dev_id, btn_id = parts[2], parts[3]
            device = next((d for d in self.state_manager.devices if d.id == dev_id), None)
            if device:
                btn = next((b for b in device.buttons if b.id == btn_id), None)
                if btn and btn.code:
                    logger.info(
                        "[HA Integration] Triggering button '%s/%s' from MQTT command.",
                        device.name,
                        btn.name,
                    )
                    self._trigger_button(device, btn, mqtt_manager)
                    return True
                else:
                    logger.warning(
                        "[HA Integration] Received command for unknown button %s on device %s.",
                        btn_id,
                        dev_id,
                    )
            else:
                logger.warning("[HA Integration] Received command for unknown device %s.", dev_id)
        return False

    def publish_button_event(self, device: IRDevice, button: IRButton, mqtt_manager):
        # For 'last_button' sensor
        topic = f"ir2mqtt/status/{device.id}/last_button"
        payload = button.name
        logger.debug("[HA Integration] Publishing last_button event to '%s': %s", topic, payload)
        mqtt_manager.publish(topic, payload)

        # For device automations (triggers)
        if button.is_event:
            event_topic = f"ir2mqtt/events/{device.id}"
            event_payload = button.name
            logger.debug(
                "[HA Integration] Publishing device automation event to '%s': %s",
                event_topic,
                event_payload,
            )
            mqtt_manager.publish(event_topic, event_payload)

    def publish_input_state(self, device: IRDevice, button: IRButton, state: str, mqtt_manager):
        # For binary_sensor state
        topic = f"ir2mqtt/input/{device.id}/{button.id}/state"
        logger.debug("[HA Integration] Publishing input state to '%s': %s", topic, state)
        mqtt_manager.publish(topic, state)

    def publish_automation_event(self, automation: IRAutomation, event_name: str, run_id: str, mqtt_manager):
        safe_event_name = sanitize_topic_part(event_name)
        base_topic = f"ir2mqtt/automation_event/{automation.id}/{safe_event_name}"

        attr_payload = {
            "event_name": event_name,
            "automation_id": automation.id,
            "automation_name": automation.name,
            "run_id": run_id,
            "timestamp": time.time(),
        }
        attr_topic = f"{base_topic}/attributes"
        state_topic = f"{base_topic}/state"

        logger.info(
            "[HA Integration] Firing event '%s' for automation '%s'.",
            event_name,
            automation.name,
        )
        logger.debug("Publishing to topics: %s and %s", attr_topic, state_topic)

        mqtt_manager.publish(attr_topic, json.dumps(attr_payload))
        mqtt_manager.publish(state_topic, "press")  # Fire and forget

    def publish_automation_state(self, automation: IRAutomation, state: str, mqtt_manager):
        # For the main automation ON/OFF sensor
        topic = f"ir2mqtt/automation/{automation.id}/state"
        logger.debug(
            "[HA Integration] Publishing automation running state to '%s': %s",
            topic,
            state,
        )
        mqtt_manager.publish(topic, state, retain=True)

    async def clear_all(self, mqtt_manager):
        logger.warning("[HA Integration] Clearing ALL Home Assistant entities.")
        if not self.state_manager.devices:
            logger.info("[HA Integration] No devices to clear.")
            return

        for dev in self.state_manager.devices:
            await self.on_device_deleted(dev, mqtt_manager)
        logger.info(
            "[HA Integration] Finished clearing entities for %d devices.",
            len(self.state_manager.devices),
        )


class StandaloneIntegration(BaseIntegration):
    NAME = "standalone"

    async def on_mqtt_connect(self, mqtt_manager):
        logger.info("[Standalone] MQTT connected. No discovery to send.")

    async def on_device_updated(self, device: IRDevice, mqtt_manager):
        logger.debug("[Standalone] Device updated: '%s'. No action needed.", device.name)

    async def on_device_deleted(self, device: IRDevice, mqtt_manager):
        logger.debug("[Standalone] Device deleted: '%s'. No action needed.", device.name)

    async def on_automation_updated(self, automation: IRAutomation, mqtt_manager):
        logger.debug("[Standalone] Automation updated: '%s'. No action needed.", automation.name)

    async def on_automation_deleted(self, automation: IRAutomation, mqtt_manager):
        logger.debug(
            "[Standalone] Automation deleted: '%s'. No action needed.",
            automation.name,
        )

    async def clear_all(self, mqtt_manager):
        logger.info("[Standalone] Clearing all entities (no-op).")

    def get_subscribe_topics(self) -> list[str]:
        topics = []
        topic_style = self.settings.topic_style if self.settings else "name"
        logger.info("[Standalone] Using '%s' topic style for subscriptions.", topic_style)

        for dev in self.state_manager.devices:
            dev_part = dev.id if topic_style == "id" else sanitize_topic_part(dev.name)

            for btn in dev.buttons:
                btn_part = btn.id if topic_style == "id" else sanitize_topic_part(btn.name)
                topics.append(f"ir2mqtt/devices/{dev_part}/{btn_part}/in")

        # Automation Trigger
        auto_part = "+"  # Wildcard for all automations
        topics.append(f"ir2mqtt/automations/{auto_part}/trigger")

        logger.debug("[Standalone] Subscribing to %d topics.", len(topics))
        return topics

    def handle_message(self, topic: str, payload: str, mqtt_manager) -> bool:
        parts = topic.split("/")
        topic_style = self.settings.topic_style if self.settings else "name"

        # Handle device command: ir2mqtt/devices/{device}/{button}/in
        if len(parts) == 5 and parts[0] == "ir2mqtt" and parts[1] == "devices" and parts[4] == "in":
            dev_part, btn_part = parts[2], parts[3]

            device = None
            if topic_style == "id":
                device = next((d for d in self.state_manager.devices if d.id == dev_part), None)
            else:
                device = next(
                    (d for d in self.state_manager.devices if sanitize_topic_part(d.name) == dev_part),
                    None,
                )

            if device:
                btn = None
                if topic_style == "id":
                    btn = next((b for b in device.buttons if b.id == btn_part), None)
                else:
                    btn = next(
                        (b for b in device.buttons if sanitize_topic_part(b.name) == btn_part),
                        None,
                    )

                if btn and btn.code:
                    logger.info(
                        "[Standalone] Triggering button '%s/%s' from MQTT command.",
                        device.name,
                        btn.name,
                    )
                    self._trigger_button(device, btn, mqtt_manager)
                    return True
                else:
                    logger.warning(
                        "[Standalone] Received command for unknown button '%s' on device '%s'.",
                        btn_part,
                        dev_part,
                    )
            else:
                logger.warning("[Standalone] Received command for unknown device '%s'.", dev_part)

        # Handle automation trigger: ir2mqtt/automations/{name_or_id}/trigger
        if len(parts) == 4 and parts[0] == "ir2mqtt" and parts[1] == "automations" and parts[3] == "trigger":
            if payload.upper() == "PRESS":
                auto_part = parts[2]
                auto = None
                if topic_style == "id":
                    auto = next(
                        (a for a in mqtt_manager.automation_manager.automations if a.id == auto_part),
                        None,
                    )
                else:
                    auto = next(
                        (a for a in mqtt_manager.automation_manager.automations if sanitize_topic_part(a.name) == auto_part),
                        None,
                    )

                if auto:
                    logger.info("[Standalone] Triggering automation '%s' from MQTT.", auto.name)
                    if mqtt_manager.loop:
                        asyncio.run_coroutine_threadsafe(
                            mqtt_manager.automation_manager.trigger_from_ha(auto.id),
                            mqtt_manager.loop,
                        )
                    return True
                else:
                    logger.warning(
                        "[Standalone] Received trigger for unknown automation '%s'.",
                        auto_part,
                    )
        return False

    def publish_button_event(self, device: IRDevice, button: IRButton, mqtt_manager):
        topic_style = self.settings.topic_style if self.settings else "name"
        dev_part = device.id if topic_style == "id" else sanitize_topic_part(device.name)
        btn_part = button.id if topic_style == "id" else sanitize_topic_part(button.name)

        # Publish last button pressed
        last_btn_topic = f"ir2mqtt/devices/{dev_part}/last_button"
        logger.debug("[Standalone] Publishing to '%s': %s", last_btn_topic, button.name)
        mqtt_manager.publish(last_btn_topic, button.name)

        # Publish specific event if enabled
        if button.is_event:
            event_topic = f"ir2mqtt/devices/{dev_part}/{btn_part}/event"
            logger.debug("[Standalone] Publishing to '%s': %s", event_topic, button.name)
            mqtt_manager.publish(event_topic, button.name)

    def publish_input_state(self, device: IRDevice, button: IRButton, state: str, mqtt_manager):
        topic_style = self.settings.topic_style if self.settings else "name"
        dev_part = device.id if topic_style == "id" else sanitize_topic_part(device.name)
        btn_part = button.id if topic_style == "id" else sanitize_topic_part(button.name)
        topic = f"ir2mqtt/devices/{dev_part}/{btn_part}/out"
        logger.debug("[Standalone] Publishing to '%s': %s", topic, state)
        mqtt_manager.publish(topic, state)

    def publish_automation_event(self, automation: IRAutomation, event_name: str, run_id: str, mqtt_manager):
        topic_style = self.settings.topic_style if self.settings else "name"
        auto_part = automation.id if topic_style == "id" else sanitize_topic_part(automation.name)

        event_payload = {
            "event_name": event_name,
            "automation_id": automation.id,
            "automation_name": automation.name,
            "run_id": run_id,
            "timestamp": time.time(),
        }
        topic = f"ir2mqtt/automations/{auto_part}/event"
        payload_json = json.dumps(event_payload)
        logger.info(
            "[Standalone] Firing event '%s' for automation '%s' to topic '%s'",
            event_name,
            automation.name,
            topic,
        )
        logger.debug("[Standalone] Event payload: %s", payload_json)
        mqtt_manager.publish(topic, payload_json)

    def publish_automation_state(self, automation: IRAutomation, state: str, mqtt_manager):
        topic_style = self.settings.topic_style if self.settings else "name"
        auto_part = automation.id if topic_style == "id" else sanitize_topic_part(automation.name)
        topic = f"ir2mqtt/automations/{auto_part}/state"
        logger.debug("[Standalone] Publishing automation state to '%s': %s", topic, state)
        mqtt_manager.publish(topic, state, retain=True)


def get_integration(mode: str, state_manager, settings=None) -> BaseIntegration:
    if mode == "standalone":
        return StandaloneIntegration(state_manager, settings)
    return HomeAssistantIntegration(state_manager, settings)
