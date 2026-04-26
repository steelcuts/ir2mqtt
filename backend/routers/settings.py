import asyncio
import json
import os
from collections import Counter
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .. import config
from ..dependencies import (
    AutomationManagerDep,
    DatabaseDep,
    IrDbManagerDep,
    LoggerDep,
    MQTTManagerDep,
    SettingsDep,
    StateManagerDep,
)
from ..ha_automation_discovery import send_ha_discovery_for_all_automations
from ..integrations import get_integration
from ..models import (
    AppModeResponse,
    ImportConfigResponse,
    IRAutomation,
    IRDevice,
    LogLevelResponse,
    MqttSettings,
    MqttTestResponse,
    StatusOk,
)
from ..utils import update_options_file
from ..websockets import broadcast_ws

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api", tags=["settings"])


class AppModePayload(BaseModel):
    mode: str
    topic_style: Literal["name", "id"] | None = "name"
    migrate: bool = False
    echo_suppression_ms: int | None = None


class LogLevelPayload(BaseModel):
    log_level: str


@router.get("/settings/app", response_model=AppModeResponse)
async def get_app_mode(settings: SettingsDep):
    version = os.environ.get("APP_VERSION", "unknown")

    return AppModeResponse(
        mode=settings.app_mode,
        topic_style=settings.topic_style,
        locked="SUPERVISOR_TOKEN" in os.environ,
        log_level=config.get_log_level_name(),
        echo_suppression_ms=settings.echo_suppression_ms,
        version=version,
    )


@router.put("/settings/log_level", response_model=LogLevelResponse)
async def set_log_level_endpoint(payload: LogLevelPayload, logger: LoggerDep):
    logger.info("Request to set log level to %s", payload.log_level)
    config.set_log_level(payload.log_level)
    return LogLevelResponse(log_level=payload.log_level)


@router.put("/settings/app", response_model=AppModeResponse)
async def set_app_mode(
    payload: AppModePayload,
    state: StateManagerDep,
    mqtt: MQTTManagerDep,
    automation_manager: AutomationManagerDep,
    logger: LoggerDep,
    db: DatabaseDep,
    settings: SettingsDep,
):
    logger.info(
        "Request to change app mode to '%s' (topic style: %s, migrate: %s)",
        payload.mode,
        payload.topic_style,
        payload.migrate,
    )
    if payload.mode not in ["home_assistant", "standalone"]:
        logger.error("Invalid app mode requested: '%s'", payload.mode)
        raise HTTPException(400, "Invalid mode")

    # Check for duplicates if we are switching to (or are in) standalone mode with name style
    if payload.mode == "standalone" and payload.topic_style == "name":
        logger.info("Checking for duplicate names for standalone/name mode.")
        # Check Devices
        device_names = [d.name.lower().strip() for d in state.devices]
        dev_counts = Counter(device_names)
        dup_devs = [n for n, c in dev_counts.items() if c > 1]

        # Check Buttons (per device)
        dup_btns = []
        for dev in state.devices:
            btn_names = [b.name.lower().strip() for b in dev.buttons]
            btn_counts = Counter(btn_names)
            if any(c > 1 for c in btn_counts.values()):
                dup_btns.append(dev.name)

        # Check Automations
        auto_names = [a.name.lower().strip() for a in automation_manager.automations]
        auto_counts = Counter(auto_names)
        dup_autos = [n for n, c in auto_counts.items() if c > 1]

        if dup_devs or dup_btns or dup_autos:
            if not payload.migrate:
                detail = []
                if dup_devs:
                    detail.append(f"Duplicate Devices: {', '.join(dup_devs)}")
                if dup_btns:
                    detail.append(f"Duplicate Buttons in: {', '.join(dup_btns)}")
                if dup_autos:
                    detail.append(f"Duplicate Automations: {', '.join(dup_autos)}")
                logger.warning(
                    "Duplicate names found and migration not requested. Details: %s",
                    "; ".join(detail),
                )
                raise HTTPException(409, "; ".join(detail))
            else:
                logger.info("Migrating duplicate names...")
                # Migrate: Rename duplicates
                # Devices
                used_dev_names = set()
                for dev in state.devices:
                    original_name = dev.name.strip()
                    name = original_name
                    counter = 1
                    while name.lower() in used_dev_names:
                        name = f"{original_name}_{counter}"
                        counter += 1
                    if name != original_name:
                        logger.info("Renaming device '%s' to '%s'", original_name, name)
                        dev.name = name
                    used_dev_names.add(name.lower())

                # Save renamed devices to DB
                for dev in state.devices:
                    await db.save_device(dev)
                await db.commit()

                # Buttons
                for dev in state.devices:
                    used_btn_names = set()
                    for btn in dev.buttons:
                        original_name = btn.name.strip()
                        name = original_name
                        counter = 1
                        while name.lower() in used_btn_names:
                            name = f"{original_name}_{counter}"
                            counter += 1
                        if name != original_name:
                            logger.info(
                                "Renaming button '%s' to '%s' on device '%s'",
                                original_name,
                                name,
                                dev.name,
                            )
                            btn.name = name
                        used_btn_names.add(name.lower())
                    # Save device again if buttons changed (optimized: could be done once above)
                    await db.save_device(dev)
                await db.commit()

                # Automations
                used_auto_names = set()
                for auto in automation_manager.automations:
                    original_name = auto.name.strip()
                    name = original_name
                    counter = 1
                    while name.lower() in used_auto_names:
                        name = f"{original_name}_{counter}"
                        counter += 1
                    if name != original_name:
                        logger.info("Renaming automation '%s' to '%s'", original_name, name)
                        auto.name = name
                    used_auto_names.add(name.lower())

                # Save automations to DB
                for auto in automation_manager.automations:
                    await automation_manager.update_automation(auto)

                automation_manager.save()
                await broadcast_ws({"type": "devices_updated"})
                await broadcast_ws({"type": "automations_updated"})
                logger.info("Duplicate name migration complete.")

    settings.app_mode = payload.mode
    settings.topic_style = payload.topic_style if payload.topic_style is not None else "name"

    if payload.echo_suppression_ms is not None:
        settings.echo_suppression_ms = payload.echo_suppression_ms

    # Save to options.yaml
    logger.info("Saving new app mode settings to options.yaml.")
    update_options_file(
        settings.options_file,
        {
            "app_mode": settings.app_mode,
            "topic_style": settings.topic_style,
            "echo_suppression_ms": settings.echo_suppression_ms,
        },
    )

    # Switch integration
    logger.info("Switching to '%s' integration.", settings.app_mode)
    old_integration = mqtt.integration
    if old_integration:
        logger.info("Clearing entities from old integration.")
        await old_integration.clear_all(mqtt)

    new_integration = get_integration(settings.app_mode, state, settings)
    mqtt.set_integration(new_integration)

    if mqtt.connected:
        logger.info("Re-subscribing to topics and running on_connect for new integration.")
        for topic in new_integration.get_subscribe_topics():
            mqtt.subscribe(topic)
        await new_integration.on_mqtt_connect(mqtt)
        if settings.app_mode != "standalone":
            send_ha_discovery_for_all_automations(automation_manager.automations, mqtt)

    logger.info("App mode successfully switched.")
    return AppModeResponse(
        mode=settings.app_mode,
        topic_style=settings.topic_style,
        locked="SUPERVISOR_TOKEN" in os.environ,
        log_level=config.get_log_level_name(),
        echo_suppression_ms=settings.echo_suppression_ms,
    )


@router.get("/settings/mqtt", response_model=MqttSettings)
async def get_mqtt_settings(
    logger: LoggerDep,
    settings: SettingsDep,
):
    logger.debug("Request for MQTT settings.")
    return MqttSettings(
        broker=settings.mqtt_broker,
        port=settings.mqtt_port,
        user=settings.mqtt_user,
        password=settings.mqtt_pass,
    )


@router.put("/settings/mqtt", response_model=StatusOk)
async def save_mqtt_settings(
    mqtt_settings: MqttSettings,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
    app_settings: SettingsDep,
):
    logger.info("Request to save MQTT settings.")

    # Prevent changes in supervised (HA App) environments where settings are from env vars
    if "SUPERVISOR_TOKEN" in os.environ:
        logger.warning("Attempted to save MQTT settings in a supervised environment. Ignoring.")
        raise HTTPException(403, "MQTT settings are managed by the supervisor.")
    update_options_file(
        app_settings.options_file,
        {
            "mqtt_broker": mqtt_settings.broker,
            "mqtt_port": mqtt_settings.port,
            "mqtt_user": mqtt_settings.user,
            "mqtt_pass": mqtt_settings.password,
        },
    )

    # Update the in-memory settings object so changes are reflected without a restart.
    app_settings.mqtt_broker = mqtt_settings.broker
    app_settings.mqtt_port = mqtt_settings.port
    app_settings.mqtt_user = mqtt_settings.user
    app_settings.mqtt_pass = mqtt_settings.password

    logger.info("MQTT settings saved. Triggering MQTT client reload.")
    task = asyncio.create_task(mqtt.reload())
    task.add_done_callback(lambda t: t.exception() and logger.error("MQTT reload failed: %s", t.exception(), exc_info=t.exception()))
    return StatusOk()


@router.post("/settings/mqtt/test", response_model=MqttTestResponse)
async def test_mqtt_settings(
    settings: MqttSettings,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to test MQTT connection to %s:%s", settings.broker, settings.port)
    result = await mqtt.test_connection(settings.model_dump())
    logger.info("MQTT connection test result: %s", result)
    return MqttTestResponse(**result)


@router.post("/reset", response_model=StatusOk)
async def factory_reset(
    state: StateManagerDep,
    mqtt: MQTTManagerDep,
    automation_manager: AutomationManagerDep,
    logger: LoggerDep,
    db: DatabaseDep,
    irdb_manager: IrDbManagerDep,
    settings: SettingsDep,
    keep_irdb: bool = False,
):
    logger.warning("Initiating factory reset...")

    logger.info("Clearing all integration entities (e.g., Home Assistant).")
    await mqtt.integration.clear_all(mqtt)

    # 3. Clear memory
    logger.info("Clearing in-memory data (devices, automations).")
    state.devices = []
    automation_manager.automations = []
    await db.delete_all_devices()
    await db.delete_all_automations()
    await db.commit()

    # 4. Remove files
    files_to_remove = [
        settings.options_file,
    ]
    for f_path in files_to_remove:
        if os.path.exists(f_path):
            logger.info("Removing configuration file: %s", f_path)
            os.remove(f_path)

    # Delete IRDB (skip when caller wants to preserve it, e.g. during test runs)
    if not keep_irdb:
        await irdb_manager.delete_db()

    # Reset log level to default
    config.set_log_level("INFO")

    # Clear the settings cache to force re-read on next request
    config.get_settings.cache_clear()
    logger.info("Settings cache cleared.")

    # Reset in-memory settings object
    default_settings = config.Settings()
    settings.app_mode = default_settings.app_mode
    settings.topic_style = default_settings.topic_style
    settings.echo_suppression_ms = default_settings.echo_suppression_ms
    settings.bridge_settings = default_settings.bridge_settings
    settings.log_level = default_settings.log_level
    settings.mqtt_broker = default_settings.mqtt_broker
    settings.mqtt_port = default_settings.mqtt_port
    settings.mqtt_user = default_settings.mqtt_user
    settings.mqtt_pass = default_settings.mqtt_pass
    logger.info("In-memory settings reset to defaults.")

    # 5. Broadcast updates
    await broadcast_ws({"type": "devices_updated"})
    await broadcast_ws(
        {
            "type": "bridges_updated",
            "bridges": mqtt._get_bridges_list_for_broadcast(),
        }
    )
    await broadcast_ws({"type": "irdb_updated"})

    logger.warning("Factory reset complete.")
    return StatusOk()


@router.get("/config/export")
async def export_config(
    state: StateManagerDep,
    automation_manager: AutomationManagerDep,
    logger: LoggerDep,
):
    """Provides the configuration file for download."""
    logger.info("Configuration export requested.")
    # Export from memory to ensure it works even if file doesn't exist yet
    export_data = {
        "devices": [d.model_dump() for d in state.devices],
        "automations": [a.model_dump() for a in automation_manager.automations],
    }
    json_str = json.dumps(export_data, indent=2)
    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=ir2mqtt_config.json"},
    )


@router.post("/config/import", response_model=ImportConfigResponse)
async def import_config(
    state: StateManagerDep,
    mqtt: MQTTManagerDep,
    automation_manager: AutomationManagerDep,
    logger: LoggerDep,
    db: DatabaseDep,
    settings: SettingsDep,
    file: UploadFile = File(...),
):
    """Imports a configuration file, overwriting the existing data."""
    logger.info("Configuration import requested from file: %s", file.filename)

    content = await file.read()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("Configuration import failed: Invalid JSON format. %s", e)
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

    if not isinstance(data, dict):
        logger.error("Configuration import failed: Invalid root JSON type.")
        raise HTTPException(status_code=400, detail="Invalid JSON format. Expected an object.")

    devices_data = data.get("devices", [])
    automations_data = data.get("automations", [])

    # Deduplicate Device Names & Buttons within the imported data
    logger.debug("Deduplicating names in imported config...")
    used_dev_names = set()
    for dev in devices_data:
        original_name = dev.get("name", "Unknown").strip()
        name = original_name
        counter = 1
        while name.lower() in used_dev_names:
            name = f"{original_name}_{counter}"
            counter += 1
        dev["name"] = name
        used_dev_names.add(name.lower())

        # Deduplicate Buttons
        used_btn_names = set()
        if "buttons" in dev:
            for btn in dev["buttons"]:
                original_btn_name = btn.get("name", "Button").strip()
                btn_name = original_btn_name
                btn_counter = 1
                while btn_name.lower() in used_btn_names:
                    btn_name = f"{original_btn_name}_{btn_counter}"
                    btn_counter += 1
                btn["name"] = btn_name
                used_btn_names.add(btn_name.lower())

    # Deduplicate Automations
    used_auto_names = set()
    for auto in automations_data:
        original_name = auto.get("name", "Automation").strip()
        name = original_name
        counter = 1
        while name.lower() in used_auto_names:
            name = f"{original_name}_{counter}"
            counter += 1
        auto["name"] = name
        used_auto_names.add(name.lower())
    logger.debug("Name deduplication complete.")

    # Clear old Home Assistant entities before loading new ones
    logger.info("Clearing existing integration entities before import.")
    await mqtt.integration.clear_all(mqtt)

    # Clear DB
    logger.info("Clearing database...")
    await db.delete_all_devices()
    await db.delete_all_automations()
    await db.commit()

    # Import Devices
    state.devices = []
    for d_data in devices_data:
        try:
            dev = IRDevice.model_validate(d_data)
            await db.save_device(dev)
            state.devices.append(dev)
        except Exception as e:
            logger.error("Skipping invalid device during import: %s", e)
    await db.commit()

    # Import Automations
    automation_manager.automations = []
    for a_data in automations_data:
        try:
            auto = IRAutomation.model_validate(a_data)
            await automation_manager.add_automation(auto)
        except Exception as e:
            logger.error("Skipping invalid automation during import: %s", e)

    logger.info("Re-initializing integration with new data.")
    await mqtt.integration.on_mqtt_connect(mqtt)
    await broadcast_ws({"type": "devices_updated"})
    await broadcast_ws({"type": "automations_updated"})

    logger.info(
        "Import successful: %s devices and %s automations loaded.",
        len(state.devices),
        len(automation_manager.automations),
    )
    return ImportConfigResponse(detail=f"{len(state.devices)} devices and {len(automation_manager.automations)} automations imported.")
