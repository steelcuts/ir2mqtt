import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.database import unit_of_work
from backend.dependencies import get_mqtt_manager, get_state_manager
from backend.main import app
from backend.models import IRButton, IRCode, IRDevice


def test_get_status(client: TestClient):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "mqtt_connected" in data
    assert "bridges" in data


def test_get_devices_empty(client: TestClient):
    # Override state manager dependency
    mock_state = MagicMock()
    mock_state.devices = []
    try:
        app.dependency_overrides[get_state_manager] = lambda: mock_state

        response = client.get("/api/devices")
        assert response.status_code == 200
        assert response.json() == []
    finally:
        del app.dependency_overrides[get_state_manager]


def test_get_bridges(client: TestClient):
    mock_bridges = [{"id": "bridge1", "name": "Living Room", "status": "online", "ip": None}]

    try:
        mock_mqtt = MagicMock()
        mock_mqtt._get_bridges_list_for_broadcast.return_value = mock_bridges
        app.dependency_overrides[get_mqtt_manager] = lambda: mock_mqtt

        response = client.get("/api/bridges")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "bridge1"
        assert data[0]["name"] == "Living Room"
        assert data[0]["status"] == "online"
    finally:
        app.dependency_overrides.pop(get_mqtt_manager, None)


@patch("backend.routers.devices.broadcast_ws", new_callable=AsyncMock)
def test_add_device(mock_router_ws, client: TestClient, monkeypatch, mqtt_manager, state_manager):
    mqtt_manager.integration = MagicMock()
    mqtt_manager.integration.on_device_updated = AsyncMock()
    mqtt_manager.integration.on_mqtt_connect = AsyncMock()

    state_manager.devices = []

    device_payload = {"name": "Test TV", "icon": "tv"}
    response = client.post("/api/devices", json=device_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test TV"
    assert "id" in data
    assert data["ordering"] == 0

    assert len(state_manager.devices) == 1
    assert state_manager.devices[0].name == "Test TV"
    assert state_manager.devices[0].ordering == 0

    # Add a second device to check ordering increments
    device_payload2 = {"name": "Test TV 2", "icon": "tv"}
    response2 = client.post("/api/devices", json=device_payload2)
    data2 = response2.json()
    assert data2["ordering"] == 1
    assert state_manager.devices[1].ordering == 1


@patch("backend.routers.devices.broadcast_ws", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_update_device(mock_router_ws, client: TestClient, monkeypatch, mqtt_manager, state_manager):
    from backend.models import IRDevice

    mqtt_manager.integration = MagicMock()
    mqtt_manager.integration.on_device_updated = AsyncMock()
    mqtt_manager.integration.on_mqtt_connect = AsyncMock()

    test_device = IRDevice(id="test_dev_1", name="Old Name", icon="icon1")
    state_manager.devices = [test_device]

    # Setup DB
    async with unit_of_work() as db:
        await db.save_device(test_device)

    update_payload = {"name": "New Name", "icon": "icon2", "target_bridges": ["br1"]}
    response = client.put(f"/api/devices/{test_device.id}", json=update_payload)
    assert response.status_code == 200


@patch("backend.routers.devices.broadcast_ws", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_delete_device(mock_router_ws, client: TestClient, monkeypatch, mqtt_manager, state_manager):
    from backend.models import IRDevice

    monkeypatch.setattr(mqtt_manager, "publish", lambda topic, payload, retain: None)
    mqtt_manager.integration = MagicMock()
    mqtt_manager.integration.on_device_deleted = AsyncMock()
    mqtt_manager.integration.on_mqtt_connect = AsyncMock()

    test_device = IRDevice(id="test_dev_1", name="To Be Deleted")
    state_manager.devices = [test_device]

    # Setup DB
    async with unit_of_work() as db:
        await db.save_device(test_device)

    response = client.delete(f"/api/devices/{test_device.id}")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_trigger_button(client: TestClient, monkeypatch, mqtt_manager, state_manager):
    # Setup device with button and code.
    btn = IRButton(
        id="btn1",
        name="Power",
        code=IRCode(protocol="NEC", payload={"address": "0x1", "command": "0x2"}),
    )
    dev = IRDevice(id="dev1", name="TV", buttons=[btn], target_bridges=["bridge1"])
    state_manager.devices = [dev]

    # Mock MQTT send.
    mock_send = AsyncMock()
    monkeypatch.setattr(mqtt_manager, "send_ir_code", mock_send)

    # Test default trigger (uses device target).
    response = client.post(f"/api/devices/{dev.id}/buttons/{btn.id}/trigger")
    assert response.status_code == 200
    mock_send.assert_called_with(btn.code.model_dump(exclude_none=True), target=["bridge1"])

    # Test targeted trigger.
    response = client.post(f"/api/devices/{dev.id}/buttons/{btn.id}/trigger?targets=bridge2")
    assert response.status_code == 200
    mock_send.assert_called_with(btn.code.model_dump(exclude_none=True), target=["bridge2"])


def test_trigger_button_not_found(client: TestClient, state_manager):
    state_manager.devices = []
    response = client.post("/api/devices/nonexistent/buttons/nonexistent/trigger")
    assert response.status_code == 404


def test_bridge_management(client: TestClient, monkeypatch, mqtt_manager):
    # Setup mock bridges.
    mqtt_manager.bridges.clear()
    mqtt_manager.bridges["bridge1"] = {"status": "online", "ip": "1.2.3.4"}

    # Test Delete.
    def mock_publish_side_effect(topic, payload, retain=False):
        # When config is cleared, simulate the broker sending it back to us
        if topic == "ir2mqtt/bridge/bridge1/config" and payload == "":
            # Create a mock message
            msg = MagicMock()
            msg.topic = topic
            msg.payload = b""
            # Trigger on_message, patching broadcast to avoid async issues
            with patch.object(mqtt_manager, "_broadcast_bridges"):
                mqtt_manager.on_message(None, None, msg)

    with patch.object(mqtt_manager, "publish", side_effect=mock_publish_side_effect) as mock_pub:
        response = client.delete("/api/bridges/bridge1")
        assert response.status_code == 200
        assert "bridge1" not in mqtt_manager.bridges
        mock_pub.assert_called()

    # Test Delete Non-existent.
    response = client.delete("/api/bridges/nonexistent")
    assert response.status_code == 404


def test_set_bridge_protocols(client: TestClient, mqtt_manager):
    mock_send_command = AsyncMock()
    mock_send_command.return_value = {"success": True}
    mqtt_manager.bridges["bridge1"] = {
        "online": True,
        "capabilities": ["nec", "raw"],
    }

    with patch.object(mqtt_manager, "send_command", mock_send_command):
        response = client.post("/api/bridges/bridge1/protocols", json={"protocols": ["nec", "raw"]})
        assert response.status_code == 200
        mock_send_command.assert_called_once()

    # Test invalid bridge
    response = client.post("/api/bridges/invalid/protocols", json={"protocols": []})
    assert response.status_code == 404


def test_reorder_devices(client: TestClient, monkeypatch, state_manager):
    d1 = IRDevice(id="d1", name="1")
    d2 = IRDevice(id="d2", name="2")
    state_manager.devices = [d1, d2]

    response = client.put("/api/devices/order", json={"ids": ["d2", "d1"]})
    assert response.status_code == 200
    assert state_manager.devices[0].id == "d2"
    assert state_manager.devices[1].id == "d1"


@pytest.mark.asyncio
async def test_duplicate_device(client: TestClient, monkeypatch, mqtt_manager, state_manager):
    d1 = IRDevice(id="d1", name="Original", buttons=[IRButton(id="b1", name="Btn", ordering=0)], ordering=0)
    d2 = IRDevice(id="d2", name="Other", buttons=[], ordering=1)
    state_manager.devices = [d1, d2]

    # Setup DB
    async with unit_of_work() as db:
        await db.save_device(d1)
        await db.save_device(d2)

    mqtt_manager.integration = MagicMock()
    mqtt_manager.integration.on_device_updated = AsyncMock()
    mqtt_manager.integration.on_mqtt_connect = AsyncMock()

    response = client.post("/api/devices/d1/duplicate")
    assert response.status_code == 200
    data = response.json()
    assert data["device"]["name"] == "Original (Copy)"
    assert len(state_manager.devices) == 3
    assert state_manager.devices[1].name == "Original (Copy)"
    assert state_manager.devices[1].ordering == 1
    assert state_manager.devices[2].name == "Other"
    assert state_manager.devices[2].ordering == 2
    assert state_manager.devices[1].buttons[0].id != "b1"  # New ID generated

    # Duplicate again to test unique names
    response = client.post("/api/devices/d1/duplicate")
    assert response.status_code == 200
    data = response.json()
    assert data["device"]["name"] == "Original (Copy 2)"
    assert len(state_manager.devices) == 4
    assert state_manager.devices[1].name == "Original (Copy 2)"
    assert state_manager.devices[1].ordering == 1
    assert state_manager.devices[2].name == "Original (Copy)"
    assert state_manager.devices[2].ordering == 2
    assert state_manager.devices[3].name == "Other"
    assert state_manager.devices[3].ordering == 3


def test_learning_flow(client: TestClient, state_manager):
    # Start Learning
    response = client.post("/api/learn?bridges=test_bridge")
    assert response.status_code == 200
    assert state_manager.learning_bridges == ["test_bridge"]

    # Cancel Learning
    response = client.post("/api/learn/cancel")
    assert response.status_code == 200
    assert state_manager.learning_bridges == []


@pytest.mark.asyncio
async def test_assign_last_code(client: TestClient, monkeypatch, state_manager):
    d1 = IRDevice(id="d1", name="TV", buttons=[IRButton(id="b1", name="Power")])
    state_manager.devices = [d1]

    # Setup DB
    async with unit_of_work() as db:
        await db.save_device(d1)

    # Fail no code
    state_manager.last_learned_code = None
    response = client.post("/api/devices/d1/buttons/b1/assign_code")
    assert response.status_code == 400

    # Success with learned code (FW sends flat — migration validator handles it)
    state_manager.last_learned_code = {
        "protocol": "NEC",
        "address": "0x1",
        "command": "0x2",
    }
    response = client.post("/api/devices/d1/buttons/b1/assign_code")
    assert response.status_code == 200
    assert state_manager.devices[0].buttons[0].code.protocol == "NEC"
    assert state_manager.last_learned_code is None  # Should be cleared

    # Success with explicit payload
    payload = {"code": {"protocol": "Sony", "payload": {"data": "0x123", "nbits": 12}}}
    response = client.post("/api/devices/d1/buttons/b1/assign_code", json=payload)
    assert response.status_code == 200
    assert state_manager.devices[0].buttons[0].code.protocol == "Sony"


def test_factory_reset(client: TestClient, mqtt_manager, automation_manager, state_manager):
    state_manager.devices = [IRDevice(id="d1", name="D1")]
    automation_manager.automations = [MagicMock()]
    original_irdb_manager = app.state.irdb_manager
    try:
        with patch("os.remove"), patch.object(mqtt_manager, "publish"), patch("backend.routers.settings.broadcast_ws", new_callable=AsyncMock):
            mqtt_manager.integration = MagicMock()
            mqtt_manager.integration.clear_all = AsyncMock()

            # Mock IRDB manager in app state
            mock_irdb = MagicMock()
            mock_irdb.delete_db = AsyncMock()
            app.state.irdb_manager = mock_irdb

            response = client.post("/api/reset")
            assert response.status_code == 200
            assert len(state_manager.devices) == 0
            assert len(automation_manager.automations) == 0
            mock_irdb.delete_db.assert_called_once()
    finally:
        app.state.irdb_manager = original_irdb_manager


def test_export_config(client: TestClient, state_manager):
    state_manager.devices = [IRDevice(id="d1", name="ExportMe")]
    response = client.get("/api/config/export")
    assert response.status_code == 200
    data = response.json()
    assert "devices" in data
    assert data["devices"][0]["name"] == "ExportMe"


def test_import_config(client: TestClient, mqtt_manager, automation_manager, state_manager):
    config_data = {
        "devices": [{"id": "new1", "name": "Imported", "buttons": []}],
        "automations": [],
    }
    file_content = json.dumps(config_data).encode("utf-8")

    mqtt_manager.integration = MagicMock()
    mqtt_manager.integration.clear_all = AsyncMock()
    mqtt_manager.integration.on_mqtt_connect = AsyncMock()

    response = client.post(
        "/api/config/import",
        files={"file": ("config.json", file_content, "application/json")},
    )
    assert response.status_code == 200
    assert len(state_manager.devices) == 1
    assert state_manager.devices[0].name == "Imported"


def test_irdb_endpoints(client: TestClient):
    original_irdb_manager = app.state.irdb_manager
    try:
        # Status.
        response = client.get("/api/irdb/status")
        assert response.status_code == 200

        # Mock the manager in app.state
        mock_manager = MagicMock()
        mock_manager.update = AsyncMock()
        mock_manager.exists = AsyncMock(return_value=False)
        mock_manager.get_stats = AsyncMock(return_value={"total_remotes": 0, "total_codes": 0, "last_updated": None, "protocols": {}})
        mock_manager.list_path = AsyncMock(return_value=[{"name": "test", "type": "dir", "path": "test"}])
        mock_manager.search = AsyncMock(return_value=[{"name": "res", "path": "res"}])
        mock_manager.parse_file = AsyncMock(return_value=[{"name": "btn"}])

        app.state.irdb_manager = mock_manager

        # Update (Mocked)
        response = client.post("/api/irdb/sync", json={"flipper": True, "probono": False})
        assert response.status_code == 200
        mock_manager.update.assert_called_with(flipper=True, probono=False)

        # Browse
        response = client.get("/api/irdb/browse?path=foo")
        assert response.status_code == 200
        assert response.json() == [{"name": "test", "type": "dir", "path": "test"}]
        mock_manager.list_path.assert_called_with("foo")

        # Search.
        response = client.get("/api/irdb/search?q=tv")
        assert response.status_code == 200
        assert response.json() == [{"name": "res", "path": "res"}]

        # File.
        response = client.get("/api/irdb/file?path=a/b.json")
        assert response.status_code == 200
        assert response.json() == [{"name": "btn"}]
    finally:
        app.state.irdb_manager = original_irdb_manager


def test_websocket_events(client: TestClient):
    # Basic connection test.
    with client.websocket_connect("/ws/events") as websocket:
        data = websocket.receive_json()
        # Messages might come in different order or extra messages might be present
        messages = [data, websocket.receive_json()]
        types = [m["type"] for m in messages]
        assert "mqtt_status" in types
        assert "bridges_updated" in types


def test_set_app_mode_simple(client: TestClient):
    response = client.put("/api/settings/app", json={"mode": "standalone", "topic_style": "id", "echo_suppression_ms": 200})
    assert response.status_code == 200
    assert response.json()["mode"] == "standalone"
    assert response.json()["topic_style"] == "id"
    assert response.json()["echo_suppression_ms"] == 200


def test_set_app_mode_duplicate_check(client: TestClient, state_manager):
    from backend.models import IRDevice

    # Setup duplicates in state_manager
    d1 = IRDevice(id="d1", name="TV")
    d2 = IRDevice(id="d2", name="TV")
    state_manager.devices = [d1, d2]

    # Try to switch to standalone name mode -> Should fail
    response = client.put("/api/settings/app", json={"mode": "standalone", "topic_style": "name"})
    assert response.status_code == 409
    assert "Duplicate Devices" in response.json()["detail"]


def test_set_app_mode_migration(client: TestClient, state_manager, monkeypatch):
    from backend.models import IRDevice

    d1 = IRDevice(id="d1", name="TV")
    d2 = IRDevice(id="d2", name="TV")
    state_manager.devices = [d1, d2]

    # Migrate -> Should succeed and rename
    response = client.put(
        "/api/settings/app",
        json={"mode": "standalone", "topic_style": "name", "migrate": True},
    )
    assert response.status_code == 200

    # Verify renaming happened in state
    names = [d.name for d in state_manager.devices]
    assert "TV" in names
    assert "TV_1" in names


@pytest.mark.asyncio
async def test_button_management(client: TestClient, monkeypatch, mqtt_manager, state_manager):
    mqtt_manager.integration = MagicMock()
    mqtt_manager.integration.on_device_updated = AsyncMock()
    mqtt_manager.integration.on_mqtt_connect = AsyncMock()
    mqtt_manager.integration.get_subscribe_topics.return_value = []

    # Create device
    dev = IRDevice(id="dev1", name="TV", buttons=[])
    state_manager.devices = [dev]

    # Setup DB
    async with unit_of_work() as db:
        await db.save_device(dev)

    # 1. Add Button
    btn_payload = {
        "name": "Power",
        "icon": "power",
        "code": {"protocol": "nec", "payload": {"data": "0x1"}},
    }
    response = client.post("/api/devices/dev1/buttons", json=btn_payload)
    assert response.status_code == 200
    btn_data = response.json()
    assert btn_data["name"] == "Power"
    btn_id = btn_data["id"]
    assert len(state_manager.devices[0].buttons) == 1
    assert state_manager.devices[0].buttons[0].ordering == 0

    # Add a second button
    btn_payload2 = {
        "name": "Volume Up",
        "icon": "volume-plus",
        "code": {"protocol": "nec", "payload": {"data": "0x2"}},
    }
    response2 = client.post("/api/devices/dev1/buttons", json=btn_payload2)
    assert response2.status_code == 200
    assert response2.json()["ordering"] == 1
    assert len(state_manager.devices[0].buttons) == 2
    assert state_manager.devices[0].buttons[1].ordering == 1

    # 2. Update Button
    update_payload = {"name": "Power Off", "icon": "power-off"}
    response = client.put(f"/api/devices/dev1/buttons/{btn_id}", json=update_payload)
    assert response.status_code == 200
    assert state_manager.devices[0].buttons[0].name == "Power Off"

    # 3. Duplicate Button
    response = client.post(f"/api/devices/dev1/buttons/{btn_id}/duplicate")
    assert response.status_code == 200
    assert len(state_manager.devices[0].buttons) == 3
    assert state_manager.devices[0].buttons[0].name == "Power Off"
    assert state_manager.devices[0].buttons[0].ordering == 0
    assert state_manager.devices[0].buttons[1].name == "Power Off (Copy)"
    assert state_manager.devices[0].buttons[1].ordering == 1
    assert state_manager.devices[0].buttons[2].name == "Volume Up"
    assert state_manager.devices[0].buttons[2].ordering == 2

    # Duplicate again to check unique name
    response = client.post(f"/api/devices/dev1/buttons/{btn_id}/duplicate")
    assert response.status_code == 200
    assert len(state_manager.devices[0].buttons) == 4
    assert state_manager.devices[0].buttons[1].name == "Power Off (Copy 2)"
    assert state_manager.devices[0].buttons[1].ordering == 1
    assert state_manager.devices[0].buttons[2].name == "Power Off (Copy)"
    assert state_manager.devices[0].buttons[2].ordering == 2
    assert state_manager.devices[0].buttons[3].name == "Volume Up"
    assert state_manager.devices[0].buttons[3].ordering == 3

    # 4. Reorder Buttons
    b1_id = state_manager.devices[0].buttons[0].id
    b2_id = state_manager.devices[0].buttons[1].id
    response = client.put("/api/devices/dev1/buttons/order", json={"ids": [b2_id, b1_id]})
    assert response.status_code == 200
    assert state_manager.devices[0].buttons[0].id == b2_id

    # 5. Delete Button
    response = client.delete(f"/api/devices/dev1/buttons/{b1_id}")
    assert response.status_code == 200
    assert len(state_manager.devices[0].buttons) == 3


def test_automation_extras(client: TestClient, monkeypatch, mqtt_manager, automation_manager):
    mqtt_manager.integration = MagicMock()
    mqtt_manager.integration.on_automation_updated = AsyncMock()
    mqtt_manager.integration.on_mqtt_connect = AsyncMock()
    mqtt_manager.integration.get_subscribe_topics.return_value = []

    from backend.models import IRAutomation

    auto1 = IRAutomation(id="auto1", name="Test Auto", actions=[], ordering=0)
    auto2 = IRAutomation(id="auto2", name="Other Auto", actions=[], ordering=1)
    automation_manager.automations = [auto1, auto2]

    # Duplicate
    response = client.post("/api/automations/auto1/duplicate")
    assert response.status_code == 200
    assert len(automation_manager.automations) == 3
    assert automation_manager.automations[1].name == "Test Auto (Copy)"
    assert automation_manager.automations[1].ordering == 1
    assert automation_manager.automations[2].name == "Other Auto"
    assert automation_manager.automations[2].ordering == 2

    # Duplicate again
    response = client.post("/api/automations/auto1/duplicate")
    assert response.status_code == 200
    assert len(automation_manager.automations) == 4
    assert automation_manager.automations[1].name == "Test Auto (Copy 2)"
    assert automation_manager.automations[1].ordering == 1
    assert automation_manager.automations[2].name == "Test Auto (Copy)"
    assert automation_manager.automations[2].ordering == 2
    assert automation_manager.automations[3].name == "Other Auto"
    assert automation_manager.automations[3].ordering == 3

    # Trigger
    # Mock trigger_from_ha
    with patch.object(automation_manager, "trigger_from_ha", new_callable=AsyncMock) as mock_trigger:
        response = client.post("/api/automations/auto1/trigger")
        assert response.status_code == 200
        mock_trigger.assert_called_once_with("auto1", source="API")


def test_mqtt_settings_endpoints(client: TestClient, monkeypatch):
    from backend.config import Settings, get_settings
    from backend.dependencies import get_settings as get_settings_dep

    # Override the dependency to create a new Settings instance on each request,
    # which will pick up monkeypatched env vars.
    def settings_override():
        return Settings()

    app.dependency_overrides[get_settings_dep] = settings_override
    get_settings.cache_clear()

    try:
        # Get
        monkeypatch.setenv("MQTT_BROKER", "env_broker")
        response = client.get("/api/settings/mqtt")
        assert response.status_code == 200
        assert response.json()["broker"] == "env_broker"
        monkeypatch.delenv("MQTT_BROKER")

        # Save
        with patch("backend.routers.settings.update_options_file") as mock_update:
            with patch("backend.mqtt.MQTTManager.reload", new_callable=AsyncMock) as mock_reload:
                payload = {"broker": "new_broker", "port": 1883, "user": "u", "password": "p"}
                response = client.put("/api/settings/mqtt", json=payload)
                assert response.status_code == 200
                mock_update.assert_called()
                mock_reload.assert_called()
    finally:
        del app.dependency_overrides[get_settings_dep]
        get_settings.cache_clear()


def test_get_app_mode(client: TestClient):
    response = client.get("/api/settings/app")
    assert response.status_code == 200
    data = response.json()
    assert "mode" in data
    assert "echo_suppression_ms" in data


def test_diagnostics_endpoints(client: TestClient, mqtt_manager, state_manager):
    # Setup
    mqtt_manager.bridges["tx1"] = {"online": True}
    mqtt_manager.bridges["rx1"] = {"online": True}
    state_manager.test_task = None

    # 1. Start test successfully
    with patch("backend.routers.diagnostics.run_loopback_test", new_callable=AsyncMock):
        response = client.post("/api/test/loopback?tx=tx1&rx=rx1")
        assert response.status_code == 200
        assert response.json()["status"] == "started"
        assert state_manager.test_task is not None  # asyncio.create_task is called

    # 2. Start test with missing bridge
    response = client.post("/api/test/loopback?tx=tx1&rx=nonexistent")
    assert response.status_code == 404

    # 3. Stop test
    mock_task = MagicMock()
    mock_task.done.return_value = False
    state_manager.test_task = mock_task
    response = client.delete("/api/test/loopback")
    assert response.status_code == 200
    assert response.json()["status"] == "stopping"
    mock_task.cancel.assert_called_once()


def test_set_log_level(client: TestClient):
    response = client.put("/api/settings/log_level", json={"log_level": "DEBUG"})
    assert response.status_code == 200
    assert response.json()["log_level"] == "DEBUG"


def test_mqtt_test_connection_endpoint(client: TestClient, mqtt_manager):
    with patch.object(mqtt_manager, "test_connection", new_callable=AsyncMock) as mock_test:
        mock_test.return_value = {"status": "ok", "message": "Connected successfully."}
        payload = {"broker": "h", "port": 1, "user": "u", "password": "p"}
        response = client.post("/api/settings/mqtt/test", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_import_config_errors(client: TestClient):
    # Invalid JSON
    response = client.post(
        "/api/config/import",
        files={"file": ("config.json", b"{invalid", "application/json")},
    )
    assert response.status_code == 400

    # Invalid Root Type (string instead of list/dict)
    response = client.post(
        "/api/config/import",
        files={"file": ("config.json", b'"string"', "application/json")},
    )
    assert response.status_code == 400
