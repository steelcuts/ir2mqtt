import asyncio
import json
import logging
import uuid
from collections.abc import Callable

import serial_asyncio

from .bridge_manager import BridgeManager, BridgeTransport

logger = logging.getLogger(__name__)


class SerialTransport(BridgeTransport):
    def __init__(
        self,
        port: str,
        baudrate: int,
        bridge_manager: BridgeManager,
        loop: asyncio.AbstractEventLoop,
        on_identified: Callable[[str], None] | None = None,
    ):
        self.port = port
        self.baudrate = baudrate
        self.bridge_manager = bridge_manager
        self.loop = loop
        self.on_identified = on_identified

        self.bridge_id = None
        self.ready_event = asyncio.Event()

        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.connected = False
        self._closing = False

        self.read_task: asyncio.Task | None = None
        self.heartbeat_task: asyncio.Task | None = None
        self.reconnect_task: asyncio.Task | None = None

        self.pending_requests: dict[str, asyncio.Event] = {}
        self.pending_responses: dict[str, dict] = {}

    def start(self):
        """Starts the connection loop in the background."""
        if self.reconnect_task is None or self.reconnect_task.done():
            self._closing = False
            self.bridge_manager.register_configured_serial(self.port, self.baudrate)
            self.reconnect_task = self.loop.create_task(self._connect_loop())

    async def stop(self):
        """Stops the connection loop and disconnects."""
        self._closing = True
        self.connected = False
        self.bridge_manager.unregister_configured_serial(self.port)

        if self.reconnect_task:
            self.reconnect_task.cancel()
        if self.read_task:
            self.read_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()

        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass

        self.reader = None
        self.writer = None

        if self.bridge_id:
            self.bridge_manager.update_bridge(self.bridge_id, {"online": False})

    async def _connect_loop(self):
        while not self._closing:
            try:
                logger.info("Connecting to serial port %s at %d baud...", self.port, self.baudrate)
                self.reader, self.writer = await serial_asyncio.open_serial_connection(url=self.port, baudrate=self.baudrate)
                self.connected = True
                logger.info("Successfully connected to serial port %s", self.port)

                # Request initial config immediately in case the device didn't reset on connect
                if self.writer:
                    self.writer.write(b'{"command": "get_config"}\n')
                    await self.writer.drain()

                # Start reading and heartbeat
                self.read_task = self.loop.create_task(self._read_loop())
                self.heartbeat_task = self.loop.create_task(self._heartbeat_loop())

                # Wait until the read loop finishes (which happens on disconnect/error)
                await self.read_task
            except Exception as e:
                if not self._closing:
                    logger.error("Error connecting to serial port %s: %s", self.port, e)

            if not self._closing:
                self.connected = False
                if self.bridge_id:
                    self.bridge_manager.update_bridge(self.bridge_id, {"online": False})
                logger.info("Reconnecting to %s in 5 seconds...", self.port)
                await asyncio.sleep(5)

    async def _read_loop(self):
        try:
            while self.connected and not self._closing and self.reader:
                line = await self.reader.readline()
                if not line:
                    logger.warning("Serial port %s EOF reached.", self.port)
                    break

                line_str = line.decode(errors="ignore").strip()
                if not line_str:
                    continue

                try:
                    payload = json.loads(line_str)
                    self._handle_message(payload)
                except json.JSONDecodeError:
                    logger.debug("Received non-JSON data from %s: %s", self.port, line_str)
                except Exception as e:
                    logger.error("Error handling message from %s: %s", self.port, e)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Read error on %s: %s", self.port, e)
        finally:
            self.connected = False

    async def _heartbeat_loop(self):
        """Sends a ping/status request every 5 seconds to check if bridge is alive."""
        try:
            while self.connected and not self._closing:
                await asyncio.sleep(5)
                if self.connected and self.bridge_id:
                    # Just an example ping, bridge should respond with its state or a ping response
                    await self.send_command(self.bridge_id, "ping", {})
        except asyncio.CancelledError:
            pass

    def _handle_message(self, payload: dict):
        if self.bridge_id:
            self.bridge_manager.update_last_seen(self.bridge_id)

        # We expect messages to either be standard JSON responses or
        # specific types like 'config', 'state', 'received', 'response'
        # To make it compatible with MQTT-like behavior, the bridge should send {"type": "..."}
        # If it doesn't have a type but has request_id, it's a response.

        msg_type = payload.get("type")
        request_id = payload.get("request_id")

        # Resolve any pending request first, regardless of message type.
        # ping/get_state responses carry both a request_id AND state fields,
        # so we must not let the state branch swallow them before resolving.
        if request_id and request_id in self.pending_requests:
            self.pending_responses[request_id] = payload
            if self.loop:
                self.loop.call_soon_threadsafe(self.pending_requests[request_id].set)

        if msg_type == "config":
            device_id = payload.get("id")
            if not device_id:
                logger.warning("Config message from %s missing 'id'", self.port)
                return

            if not self.bridge_id:
                self.bridge_id = device_id
                self.bridge_manager.register_transport(self.bridge_id, self)
                self.ready_event.set()
                if self.on_identified:
                    self.on_identified(self.bridge_id)
            elif self.bridge_id != device_id:
                logger.warning("Serial bridge ID changed from %s to %s", self.bridge_id, device_id)
                if self.on_identified:
                    self.on_identified(device_id)

            payload["id"] = self.bridge_id
            payload["online"] = True
            payload["connection_type"] = "serial"
            payload["serial_port"] = self.port
            if "name" not in payload:
                payload["name"] = self.bridge_id
            self.bridge_manager.update_bridge(self.bridge_id, payload)

        elif msg_type == "state":
            if self.bridge_id:
                payload["online"] = True
                self.bridge_manager.update_bridge(self.bridge_id, payload)

        elif msg_type == "received":
            if not self.bridge_id:
                return
            # It's an IR received message
            # Clean up the envelope if it was wrapped in a "received" type
            received_payload = payload.get("data", payload) if msg_type == "received" else payload
            if self.bridge_manager.on_message_cb:
                self.bridge_manager.on_message_cb(self.bridge_id, "received", received_payload)
            else:
                logger.warning("No message callback registered in BridgeManager for received code")

    async def send_command(self, bridge_id: str, command: str, payload: dict | str) -> dict | None:
        if not self.connected or not self.writer:
            logger.warning("Cannot send command to %s, port is not connected.", self.port)
            return None

        request_id = str(uuid.uuid4())
        cmd_payload = {
            "type": "command",
            "command": command,
            "request_id": request_id,
        }

        if isinstance(payload, dict):
            cmd_payload.update(payload)

        data_str = json.dumps(cmd_payload) + "\n"

        event = asyncio.Event()
        self.pending_requests[request_id] = event

        try:
            self.writer.write(data_str.encode())
            await self.writer.drain()
            logger.debug("Sent command to %s: %s", self.port, data_str.strip())

            # Wait for response if needed (we'll wait up to 2 seconds)
            try:
                await asyncio.wait_for(event.wait(), timeout=2.0)
                response = self.pending_responses.get(request_id)
                logger.debug("Received response for %s: %s", request_id, response)
                return response
            except TimeoutError:
                logger.warning("Timeout waiting for response from %s for request %s", self.port, request_id)
                return None

        except Exception as e:
            logger.error("Error sending command to %s: %s", self.port, e)
            return None
        finally:
            self.pending_requests.pop(request_id, None)
            self.pending_responses.pop(request_id, None)
