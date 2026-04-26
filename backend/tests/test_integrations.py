import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.integrations import HomeAssistantIntegration, StandaloneIntegration
from backend.models import IRAutomation, IRButton, IRCode, IRDevice
from backend.state import StateManager


@pytest.fixture
def state_manager():
    sm = StateManager()
    dev = IRDevice(
        id="d1",
        name="TV",
        buttons=[
            IRButton(
                id="b1",
                name="Power",
                code=IRCode(protocol="nec", address="0x1", command="0x2"),
            )
        ],
    )
    sm.devices = [dev]
    return sm


@pytest.fixture
def mqtt_manager():
    async def noop(*args, **kwargs):
        pass

    mm = MagicMock()
    mm.publish = MagicMock()
    mm.send_ir_code = AsyncMock()
    mm.loop = asyncio.get_event_loop()
    return mm


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.topic_style = "name"
    return s


@pytest.mark.asyncio
async def test_ha_integration_subscribe(state_manager, mock_settings):
    integration = HomeAssistantIntegration(state_manager, mock_settings)
    topics = integration.get_subscribe_topics()
    assert "ir2mqtt/cmd/d1/b1" in topics
    assert "ir2mqtt/automation/+/trigger" in topics


@pytest.mark.asyncio
async def test_ha_integration_handle_message(state_manager, mqtt_manager, mock_settings):
    integration = HomeAssistantIntegration(state_manager, mock_settings)

    # Valid command
    res = integration.handle_message("ir2mqtt/cmd/d1/b1", "PRESS", mqtt_manager)
    assert res is True
    await asyncio.sleep(0.01)
    mqtt_manager.send_ir_code.assert_called_once()

    # Invalid topic
    res = integration.handle_message("ir2mqtt/other", "PRESS", mqtt_manager)
    assert res is False


@pytest.mark.asyncio
async def test_standalone_integration_subscribe_name(state_manager, mock_settings):
    mock_settings.topic_style = "name"
    integration = StandaloneIntegration(state_manager, mock_settings)
    topics = integration.get_subscribe_topics()
    # "TV" -> "tv", "Power" -> "power"
    assert "ir2mqtt/devices/tv/power/in" in topics


@pytest.mark.asyncio
async def test_standalone_integration_subscribe_id(state_manager, mock_settings):
    mock_settings.topic_style = "id"
    integration = StandaloneIntegration(state_manager, mock_settings)
    topics = integration.get_subscribe_topics()
    assert "ir2mqtt/devices/d1/b1/in" in topics


@pytest.mark.asyncio
async def test_standalone_integration_handle_message(state_manager, mqtt_manager, mock_settings):
    mock_settings.topic_style = "name"
    integration = StandaloneIntegration(state_manager, mock_settings)

    res = integration.handle_message("ir2mqtt/devices/tv/power/in", "PRESS", mqtt_manager)
    assert res is True
    await asyncio.sleep(0.01)
    mqtt_manager.send_ir_code.assert_called_once()


@pytest.mark.asyncio
async def test_standalone_integration_publish_event(state_manager, mqtt_manager, mock_settings):
    mock_settings.topic_style = "name"
    integration = StandaloneIntegration(state_manager, mock_settings)
    dev = state_manager.devices[0]
    btn = dev.buttons[0]

    integration.publish_button_event(dev, btn, mqtt_manager)

    mqtt_manager.publish.assert_any_call("ir2mqtt/devices/tv/last_button", "Power")
    mqtt_manager.publish.assert_any_call("ir2mqtt/devices/tv/power/event", "Power")


@pytest.mark.asyncio
async def test_ha_integration_clear_all(state_manager, mqtt_manager, mock_settings):
    integration = HomeAssistantIntegration(state_manager, mock_settings)
    await integration.clear_all(mqtt_manager)

    # Check if it published empty configs for device d1, button b1
    # We expect retained empty messages to remove entities from HA
    mqtt_manager.publish.assert_any_call("homeassistant/button/ir_d1/b1/config", "", retain=True)


@pytest.mark.asyncio
async def test_ha_integration_publish_automation_state(state_manager, mqtt_manager, mock_settings):
    integration = HomeAssistantIntegration(state_manager, mock_settings)
    auto = IRAutomation(id="a1", name="Auto")

    integration.publish_automation_state(auto, "ON", mqtt_manager)

    mqtt_manager.publish.assert_called_with("ir2mqtt/automation/a1/state", "ON", retain=True)


@pytest.mark.asyncio
async def test_ha_integration_publish_automation_event(state_manager, mqtt_manager, mock_settings):
    integration = HomeAssistantIntegration(state_manager, mock_settings)
    auto = IRAutomation(id="a1", name="Auto")

    integration.publish_automation_event(auto, "Event A", "run1", mqtt_manager)

    # Should publish attributes and state
    calls = mqtt_manager.publish.call_args_list
    topics = [c[0][0] for c in calls]

    base = "ir2mqtt/automation_event/a1/event_a"
    assert f"{base}/attributes" in topics
    assert f"{base}/state" in topics


@pytest.mark.asyncio
async def test_base_trigger_button_broadcast(mqtt_manager):
    # Test base class method via subclass instance or mock
    integration = HomeAssistantIntegration(MagicMock())
    integration.state_manager.loop = asyncio.get_event_loop()

    dev = MagicMock()
    dev.target_bridges = []
    btn = MagicMock()
    btn.code.model_dump.return_value = {"data": "0x1"}

    integration._trigger_button(dev, btn, mqtt_manager)
    await asyncio.sleep(0.01)
    mqtt_manager.send_ir_code.assert_called_with({"data": "0x1"}, target="broadcast")


@pytest.mark.asyncio
async def test_base_trigger_button_targets(mqtt_manager):
    integration = HomeAssistantIntegration(MagicMock())
    integration.state_manager.loop = asyncio.get_event_loop()

    dev = MagicMock()
    dev.target_bridges = ["br1", "br2"]
    btn = MagicMock()
    btn.code.model_dump.return_value = {"data": "0x1"}

    integration._trigger_button(dev, btn, mqtt_manager)
    await asyncio.sleep(0.01)
    assert mqtt_manager.send_ir_code.call_count == 2
    mqtt_manager.send_ir_code.assert_any_call({"data": "0x1"}, target="br1")
    mqtt_manager.send_ir_code.assert_any_call({"data": "0x1"}, target="br2")


def test_ha_handle_message_invalid(state_manager, mqtt_manager, mock_settings):
    integration = HomeAssistantIntegration(state_manager, mock_settings)

    # Unknown device
    res = integration.handle_message("ir2mqtt/cmd/unknown_dev/btn1", "PRESS", mqtt_manager)
    assert res is False

    # Unknown button
    dev = state_manager.devices[0]  # d1 from fixture
    res = integration.handle_message(f"ir2mqtt/cmd/{dev.id}/unknown_btn", "PRESS", mqtt_manager)
    assert res is False


def test_standalone_handle_message_invalid(state_manager, mqtt_manager, mock_settings):
    integration = StandaloneIntegration(state_manager, mock_settings)

    # Unknown device
    res = integration.handle_message("ir2mqtt/devices/unknown/btn/in", "PRESS", mqtt_manager)
    assert res is False

    # Unknown button
    res = integration.handle_message("ir2mqtt/devices/tv/unknown/in", "PRESS", mqtt_manager)
    assert res is False

    # Unknown automation
    mqtt_manager.automation_manager.automations = []
    res = integration.handle_message("ir2mqtt/automations/unknown/trigger", "PRESS", mqtt_manager)
    assert res is False
