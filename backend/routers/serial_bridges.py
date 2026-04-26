"""
API endpoints for serial bridge management
"""

import asyncio
import json
import logging
from typing import Any

import serial
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from serial.tools import list_ports

from ..dependencies import (
    BridgeManagerDep,
    LoggerDep,
    SettingsDep,
)
from ..models import SerialBridgeConfig
from ..serial_manager import SerialTransport
from ..utils import update_options_file
from ..websockets import broadcast_ws

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bridges/serial", tags=["serial-bridges"])


# --- Request/Response Models ---
class PortInfoResponse(BaseModel):
    port: str
    description: str
    hwid: str


class TestSerialRequest(BaseModel):
    port: str
    baudrate: int = 115200


class CreateSerialBridgeRequest(BaseModel):
    port: str
    baudrate: int = 115200
    bridge_id: str | None = None


@router.get("/ports", response_model=list[PortInfoResponse])
async def list_serial_ports():
    """Returns a list of all available serial ports."""
    ports = []
    for port_info in list_ports.comports():
        ports.append(
            PortInfoResponse(
                port=port_info.device,
                description=port_info.description or "Unknown Serial Port",
                hwid=port_info.hwid or "N/A",
            )
        )
    return ports


@router.post("/test", response_model=dict[str, Any])
async def test_serial_connection(
    payload: TestSerialRequest,
    logger: LoggerDep,
):
    """
    Tests the serial connection by trying to open the port, send a test message, and read a response.
    This can help verify that the device is responding correctly before adding it as a bridge.
    """
    port = payload.port
    baudrate = payload.baudrate

    logger.info("Testing serial connection to %s at %d baud", port, baudrate)

    try:
        # Try to open the connection briefly and send a message
        # On Mac/ESP32, opening often leads to a reboot (DTR/RTS).
        ser = serial.Serial(port=port, baudrate=baudrate, timeout=3)

        # Send a status request (if it does not reboot)
        ser.write(b'{"command": "get_config"}\n')

        # Try to read (up to 3 seconds, ignore bootloader logs)
        import time

        start_time = time.time()
        config = None
        raw_lines = []

        while time.time() - start_time < 3:
            line = ser.readline()
            if not line:
                continue

            decoded = line.decode(errors="ignore").strip()
            if decoded:
                raw_lines.append(decoded)
                if decoded.startswith("{"):
                    try:
                        config = json.loads(decoded)
                        break
                    except json.JSONDecodeError:
                        pass

        ser.close()

        if config:
            logger.info("Serial connection test successful, config: %s", config)
            return {
                "status": "success",
                "message": "Serial connection works!",
                "config": config,
            }
        elif raw_lines:
            logger.warning("Got non-JSON response from serial port: %s", raw_lines)
            return {
                "status": "success",
                "message": "Serial connection works, but response wasn't valid JSON",
                "raw_response": "\n".join(raw_lines),
            }
        else:
            logger.warning("No response from serial port %s", port)
            raise HTTPException(504, "No response from serial device. Check if the device is powered and sending data.")

    except serial.SerialException as e:
        logger.error("Serial connection failed for %s: %s", port, e)
        raise HTTPException(400, f"Failed to open serial port: {str(e)}")
    except TimeoutError:
        logger.error("Serial connection timeout for %s", port)
        raise HTTPException(504, "Timeout waiting for response from serial device")
    except Exception as e:
        logger.error("Unexpected error testing serial connection: %s", e)
        raise HTTPException(500, f"Unexpected error: {str(e)}")


@router.post("", response_model=dict[str, Any])
async def create_serial_bridge(
    request: Request,
    payload: CreateSerialBridgeRequest,
    bridge_manager: BridgeManagerDep,
    settings: SettingsDep,
    logger: LoggerDep,
):
    """
    Adds a new serial bridge to the configuration and starts the connection.
    """
    port = payload.port
    baudrate = payload.baudrate
    bridge_id = payload.bridge_id

    logger.info("Adding serial bridge: port=%s, baudrate=%d", port, baudrate)

    # Check if this port already exists in the configuration
    for existing_config in settings.serial_bridges.values():
        if existing_config.port == port:
            raise HTTPException(409, f"Serial bridge on port {port} already configured")

    # Add to settings
    target_bridge_id = bridge_id if bridge_id else f"serial:{port}"
    serial_config = SerialBridgeConfig(port=port, baudrate=baudrate)
    settings.serial_bridges[target_bridge_id] = serial_config

    # Start the connection
    def on_identified(new_bridge_id: str):
        current_key = None
        for k, c in list(settings.serial_bridges.items()):
            if c.port == port:
                current_key = k
                break
        if current_key and current_key != new_bridge_id:
            logger.warning("Serial bridge on %s changed ID: %s → %s", port, current_key, new_bridge_id)
            cfg = settings.serial_bridges.pop(current_key)
            settings.serial_bridges[new_bridge_id] = cfg
            update_options_file(settings.options_file, {"serial_bridges": {k: v.model_dump() for k, v in settings.serial_bridges.items()}})

    st = SerialTransport(port=port, baudrate=baudrate, bridge_manager=bridge_manager, loop=asyncio.get_event_loop(), on_identified=on_identified)
    if not hasattr(request.app.state, "serial_transports"):
        request.app.state.serial_transports = []
    request.app.state.serial_transports.append(st)
    st.start()

    try:
        await asyncio.wait_for(st.ready_event.wait(), timeout=5.0)
    except TimeoutError:
        logger.warning("Timeout waiting for serial bridge on port %s to report config. It will be added when it comes online.", port)

    # Persist in options.yaml
    update_options_file(settings.options_file, {"serial_bridges": {k: v.model_dump() for k, v in settings.serial_bridges.items()}})

    logger.info("Serial bridge created and started: %s", st.bridge_id)

    # Broadcastete die aktualisierte Bridge-Liste
    await broadcast_ws({"type": "bridges_updated", "bridges": bridge_manager.get_bridges_list_for_broadcast()})

    return {"status": "ok", "bridge_id": st.bridge_id or "unknown", "message": "Serial bridge created and connecting..."}


@router.delete("/{bridge_id:path}", response_model=dict[str, Any])
async def delete_serial_bridge(
    request: Request,
    bridge_id: str,
    bridge_manager: BridgeManagerDep,
    settings: SettingsDep,
    logger: LoggerDep,
):
    """
    Deletes a serial bridge from the configuration and stops the connection.
    """
    logger.info("Deleting serial bridge: %s", bridge_id)

    bridge_data = bridge_manager.get_bridge(bridge_id)

    # Determine serial port — either from live bridge data or from the synthetic
    # offline ID ("serial:<port>") that is shown when the port never connected.
    if bridge_data and bridge_data.get("connection_type") == "serial":
        serial_port = bridge_data.get("serial_port")
    elif bridge_id.startswith("serial:"):
        serial_port = bridge_id[len("serial:") :]
    else:
        raise HTTPException(400, "Only serial bridges can be deleted via this endpoint")

    # Find the corresponding config key to remove (in case the live bridge_id differs from the config key, e.g., "esp-xy" vs "serial:/dev/ttyUSB0")
    serial_config_to_remove_key = None
    for k, config in settings.serial_bridges.items():
        if config.port == serial_port:
            serial_config_to_remove_key = k
            break

    if not serial_config_to_remove_key:
        raise HTTPException(404, "Serial bridge configuration not found")

    # Remove from settings
    del settings.serial_bridges[serial_config_to_remove_key]

    # Persist to options.yaml
    update_options_file(settings.options_file, {"serial_bridges": {k: v.model_dump() for k, v in settings.serial_bridges.items()}})

    # Stop transport
    if hasattr(request.app.state, "serial_transports"):
        transport_to_remove = None
        for st in request.app.state.serial_transports:
            if st.port == serial_port:
                transport_to_remove = st
                break

        if transport_to_remove:
            await transport_to_remove.stop()
            request.app.state.serial_transports.remove(transport_to_remove)

    # Remove from Bridge Manager (both the live ID and any config key deviation)
    bridge_manager.remove_bridge(bridge_id)
    bridge_manager.unregister_configured_serial(serial_port)
    if bridge_id in bridge_manager.transports:
        del bridge_manager.transports[bridge_id]
    # If the config key differs from the bridge_id (e.g., "esp-xy" vs "serial:/dev/ttyUSB0")
    if serial_config_to_remove_key != bridge_id:
        bridge_manager.remove_bridge(serial_config_to_remove_key)

    logger.info("Serial bridge deleted: %s (port: %s)", bridge_id, serial_port)

    # Broadcast the updated bridge list
    await broadcast_ws({"type": "bridges_updated", "bridges": bridge_manager.get_bridges_list_for_broadcast()})

    return {"status": "ok", "message": f"Serial bridge {bridge_id} deleted"}
