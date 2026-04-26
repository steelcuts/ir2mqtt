import asyncio
import time
from collections.abc import Callable
from typing import Any


class BridgeTransport:
    async def send_command(self, bridge_id: str, topic_suffix: str, payload: dict | str) -> dict | None:
        raise NotImplementedError()


class BridgeManager:
    def __init__(self):
        self.bridges: dict[str, dict[str, Any]] = {}
        self.transports: dict[str, BridgeTransport] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self._broadcast_cb: Callable | None = None
        self.on_message_cb: Callable[[str, str, dict], None] | None = None
        # Serial ports that are configured but not yet connected (port → baudrate)
        self._configured_serial: dict[str, int] = {}
        # Bridge IDs that should be silently suppressed from the UI
        self.ignored_bridge_ids: set[str] = set()
        # Serial ports whose "connecting" synthetic entry should be suppressed
        self.ignored_serial_ports: set[str] = set()

    def set_ignored_bridges(self, ids: list[str]):
        self.ignored_bridge_ids = set(ids)
        self._broadcast_bridges()

    def register_configured_serial(self, port: str, baudrate: int):
        self._configured_serial[port] = baudrate
        self._broadcast_bridges()

    def unregister_configured_serial(self, port: str):
        self._configured_serial.pop(port, None)
        self._broadcast_bridges()

    def set_loop(self, loop: asyncio.AbstractEventLoop, broadcast_cb: Callable):
        self.loop = loop
        self._broadcast_cb = broadcast_cb

    def set_on_message_cb(self, cb: Callable[[str, str, dict], None]):
        self.on_message_cb = cb

    def register_transport(self, name: str, transport: BridgeTransport):
        self.transports[name] = transport

    def update_last_seen(self, bridge_id: str):
        if bridge_id not in self.bridges:
            return
        self.bridges[bridge_id]["last_seen"] = int(time.time() * 1000)

    def update_bridge(self, bridge_id: str, data: dict[str, Any]):
        """Update or create a bridge entry."""
        if bridge_id in self.ignored_bridge_ids:
            return
        if bridge_id not in self.bridges:
            self.bridges[bridge_id] = {}
        self.bridges[bridge_id].update(data)
        self._broadcast_bridges()

    def remove_bridge(self, bridge_id: str):
        if bridge_id in self.bridges:
            del self.bridges[bridge_id]
            self._broadcast_bridges()

    def get_bridge(self, bridge_id: str) -> dict[str, Any] | None:
        return self.bridges.get(bridge_id)

    def get_bridges_list_for_broadcast(self) -> list[dict]:
        bridges_with_names = []
        for bridge_id, bridge_data in self.bridges.items():
            if bridge_id in self.ignored_bridge_ids:
                continue
            name = bridge_data.get("name", bridge_id)
            bridges_with_names.append(
                {
                    "id": bridge_id,
                    "name": name,
                    "status": "online" if bridge_data.get("online") else "offline",
                    "connection_type": bridge_data.get("connection_type", "mqtt"),
                    "network_type": bridge_data.get("network_type"),
                    "ip": bridge_data.get("ip"),
                    "serial_port": bridge_data.get("serial_port"),
                    "mac": bridge_data.get("mac"),
                    "capabilities": bridge_data.get("capabilities", []),
                    "receivers": bridge_data.get("receivers", []),
                    "transmitters": bridge_data.get("transmitters", []),
                    "enabled_protocols": bridge_data.get("enabled_protocols", []),
                    "last_seen": bridge_data.get("last_seen"),
                    "version": bridge_data.get("version"),
                    "last_received": list(bridge_data.get("last_received", [])),
                    "last_sent": list(bridge_data.get("last_sent", [])),
                }
            )

        # Include configured serial ports that haven't identified yet
        registered_serial_ports = {data.get("serial_port") for data in self.bridges.values() if data.get("connection_type") == "serial"}
        for port, baudrate in self._configured_serial.items():
            if port not in registered_serial_ports:
                if port in self.ignored_serial_ports:
                    continue
                bridges_with_names.append(
                    {
                        "id": f"serial:{port}",
                        "name": port,
                        "status": "connecting",
                        "connection_type": "serial",
                        "serial_port": port,
                        "network_type": None,
                        "ip": None,
                        "mac": None,
                        "capabilities": [],
                        "receivers": [],
                        "transmitters": [],
                        "enabled_protocols": [],
                        "last_seen": None,
                        "version": None,
                        "last_received": [],
                        "last_sent": [],
                    }
                )

        return bridges_with_names

    def _broadcast_bridges(self):
        if self.loop and self.loop.is_running() and self._broadcast_cb:
            asyncio.run_coroutine_threadsafe(
                self._broadcast_cb(self.get_bridges_list_for_broadcast()),
                self.loop,
            )

    async def send_command(self, bridge_id: str, command: str, payload: dict | str) -> dict | None:
        """
        Sends a command to a bridge via its primary transport.
        """
        transport = self.transports.get(bridge_id)
        if not transport:
            transport = self.transports.get("mqtt")

        if transport:
            return await transport.send_command(bridge_id, command, payload)
        return None
