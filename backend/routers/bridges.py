import asyncio
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..dependencies import (
    BridgeManagerDep,
    DatabaseDep,
    LoggerDep,
    MQTTManagerDep,
    SettingsDep,
    StateManagerDep,
)
from ..models import Bridge, BridgeSettings
from ..utils import update_options_file
from ..websockets import broadcast_ws

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api/bridges", tags=["bridges"])


class BridgeProtocolsPayload(BaseModel):
    protocols: list[str]


@router.get("", response_model=list[Bridge])
async def get_bridges(
    mqtt: MQTTManagerDep,
    settings: SettingsDep,
):
    # Merge dynamic MQTT data with persistent settings
    bridges_list = mqtt._get_bridges_list_for_broadcast()
    for bridge in bridges_list:
        bid = bridge["id"]
        if bid in settings.bridge_settings:
            bridge["settings"] = settings.bridge_settings[bid]
    return bridges_list


@router.delete("/{bridge_id}")
async def delete_bridge(
    bridge_id: str,
    mqtt: MQTTManagerDep,
    state: StateManagerDep,
    db: DatabaseDep,
    logger: LoggerDep,
    settings: SettingsDep,
):
    logger.info("Request to delete bridge: %s", bridge_id)
    if bridge_id in mqtt.bridges:
        # Remove from internal state FIRST to avoid race condition with on_message
        del mqtt.bridges[bridge_id]

        # Publish empty retained messages to clear the config and state topics
        mqtt.publish(f"ir2mqtt/bridge/{bridge_id}/config", "", retain=True)
        mqtt.publish(f"ir2mqtt/bridge/{bridge_id}/state", "", retain=True)
        mqtt.publish(f"ir2mqtt/bridge/{bridge_id}/command", "", retain=True)
        mqtt.publish(f"ir2mqtt/bridge/{bridge_id}/response", "", retain=True)
        mqtt.publish(f"ir2mqtt/bridge/{bridge_id}/received", "", retain=True)
        mqtt.publish(f"ir2mqtt/bridge/{bridge_id}", "", retain=True)

        # Remove this bridge from any device that targets it
        for device in state.devices:
            if hasattr(device, "target_bridges") and bridge_id in device.target_bridges:
                device.target_bridges.remove(bridge_id)
                await db.save_device(device)
        await db.commit()

        logger.info("Bridge '%s' deleted and its topics cleared.", bridge_id)
        # Notify clients
        await broadcast_ws(
            {
                "type": "bridges_updated",
                "bridges": mqtt._get_bridges_list_for_broadcast(),
            }
        )
        await broadcast_ws({"type": "devices_updated"})
        return {"status": "ok"}
    else:
        logger.warning("Attempted to delete non-existent bridge: %s", bridge_id)
        raise HTTPException(404, "Bridge not found")


@router.put("/{bridge_id}/settings")
async def update_bridge_settings(
    bridge_id: str,
    payload: BridgeSettings,
    logger: LoggerDep,
    settings: SettingsDep,
):
    logger.info("Updating settings for bridge: %s", bridge_id)

    # Update in-memory config
    settings.bridge_settings[bridge_id] = payload

    # Persist to options.yaml
    serialized_settings = {k: v.model_dump() for k, v in settings.bridge_settings.items()}
    update_options_file(settings.options_file, {"bridge_settings": serialized_settings})
    return {"status": "ok", "settings": payload}


@router.get("/ignored")
async def get_ignored_bridges(settings: SettingsDep):
    return {"ignored": settings.ignored_bridges}


@router.post("/ignored/{bridge_id:path}")
async def ignore_bridge(
    request: Request,
    bridge_id: str,
    bridge_manager: BridgeManagerDep,
    settings: SettingsDep,
    logger: LoggerDep,
):
    if bridge_id in settings.ignored_bridges:
        return {"status": "ok", "ignored": settings.ignored_bridges}

    logger.info("Ignoring bridge: %s", bridge_id)

    settings.ignored_bridges.append(bridge_id)
    bridge_manager.ignored_bridge_ids.add(bridge_id)

    # Suppress the "connecting" synthetic entry in-memory (not persisted — derived on
    # startup from serial_bridges[].bridge_id instead).
    bridge_data = bridge_manager.bridges.get(bridge_id, {})
    serial_port = bridge_data.get("serial_port") if bridge_data.get("connection_type") == "serial" else None
    if not serial_port:
        # Also match synthetic offline IDs ("serial:<port>") against config entries
        for b_id, cfg in settings.serial_bridges.items():
            if b_id == bridge_id or f"serial:{cfg.port}" == bridge_id:
                serial_port = cfg.port
                break
    if serial_port:
        bridge_manager.ignored_serial_ports.add(serial_port)

        # Stop active transport if running
        if hasattr(request.app.state, "serial_transports"):
            for st in request.app.state.serial_transports:
                if st.port == serial_port:
                    await st.stop()
                    request.app.state.serial_transports.remove(st)
                    logger.info("Stopped serial transport for ignored port %s", serial_port)
                    break

    update_options_file(settings.options_file, {"ignored_bridges": settings.ignored_bridges})

    # Keep bridge in bridge_manager.bridges so its serial_port stays in
    # registered_serial_ports — this prevents the "connecting" synthetic entry
    # from being generated while the app is running.
    # update_bridge() already no-ops for ignored IDs, so the data stays stale.
    await broadcast_ws({"type": "bridges_updated", "bridges": bridge_manager.get_bridges_list_for_broadcast()})

    return {"status": "ok", "ignored": settings.ignored_bridges}


@router.delete("/ignored/{bridge_id:path}")
async def unignore_bridge(
    request: Request,
    bridge_id: str,
    bridge_manager: BridgeManagerDep,
    settings: SettingsDep,
    logger: LoggerDep,
):
    if bridge_id not in settings.ignored_bridges:
        raise HTTPException(404, "Bridge not in ignore list")

    logger.info("Unignoring bridge: %s", bridge_id)

    settings.ignored_bridges.remove(bridge_id)
    bridge_manager.ignored_bridge_ids.discard(bridge_id)

    # Also clear the in-memory serial port suppression
    serial_port = bridge_manager.bridges.get(bridge_id, {}).get("serial_port")
    if not serial_port:
        for b_id, cfg in settings.serial_bridges.items():
            if b_id == bridge_id or f"serial:{cfg.port}" == bridge_id:
                serial_port = cfg.port
                break
    if serial_port:
        bridge_manager.ignored_serial_ports.discard(serial_port)

        # Restart active transport if it is configured
        cfg = None
        for b_id, c in settings.serial_bridges.items():
            if c.port == serial_port:
                cfg = c
                break
        if cfg:
            from ..serial_manager import SerialTransport

            def on_identified(new_bridge_id: str):
                current_key = None
                for k, c in list(settings.serial_bridges.items()):
                    if c.port == serial_port:
                        current_key = k
                        break
                if current_key and current_key != new_bridge_id:
                    logger.warning("Serial bridge on %s changed ID: %s → %s", serial_port, current_key, new_bridge_id)
                    c_val = settings.serial_bridges.pop(current_key)
                    settings.serial_bridges[new_bridge_id] = c_val
                    update_options_file(settings.options_file, {"serial_bridges": {k: v.model_dump() for k, v in settings.serial_bridges.items()}})

            st = SerialTransport(port=serial_port, baudrate=cfg.baudrate, bridge_manager=bridge_manager, loop=asyncio.get_event_loop(), on_identified=on_identified)
            if not hasattr(request.app.state, "serial_transports"):
                request.app.state.serial_transports = []
            request.app.state.serial_transports.append(st)
            st.start()
            logger.info("Started serial transport for unignored port %s", serial_port)

    update_options_file(settings.options_file, {"ignored_bridges": settings.ignored_bridges})

    # Request fresh config from the bridge so it repopulates immediately.
    # The response flows through _handle_message → update_bridge → broadcast.
    # Fire-and-forget: don't block the HTTP response waiting for the bridge to reply.
    asyncio.create_task(bridge_manager.send_command(bridge_id, "get_config", {}))

    # Broadcast now so the ignore button disappears; the bridge card itself
    # will appear once the config reply arrives via the task above.
    await broadcast_ws({"type": "bridges_updated", "bridges": bridge_manager.get_bridges_list_for_broadcast()})

    return {"status": "ok", "ignored": settings.ignored_bridges}


@router.post("/{bridge_id}/protocols")
async def set_bridge_protocols(
    bridge_id: str,
    payload: BridgeProtocolsPayload,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to set protocols for bridge %s to: %s", bridge_id, payload.protocols)
    bridge_data = mqtt.bridges.get(bridge_id, {})
    if not bridge_data:
        raise HTTPException(404, "Bridge not found")

    if not bridge_data.get("online"):
        raise HTTPException(409, "Bridge is offline")

    # Send command and wait for a quick acknowledgement
    response = await mqtt.bridge_manager.send_command(bridge_id, "set_protocols", {"protocols": payload.protocols})

    if response is None:
        raise HTTPException(504, "Bridge did not respond in time.")

    if not response.get("success"):
        raise HTTPException(
            400,
            f"Bridge failed to set protocols: {response.get('error', 'Unknown error')}",
        )

    logger.info("Command to set protocols for bridge %s accepted.", bridge_id)
    return {"status": "ok", "detail": "Command sent and acknowledged by bridge."}
