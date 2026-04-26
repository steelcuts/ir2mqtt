import json
import os
import random
import threading
import time
import uuid
from collections.abc import Callable

try:
    import pty
    import termios

    PTY_SUPPORTED = True
except ImportError:
    PTY_SUPPORTED = False

from pydantic import BaseModel, Field

from tools.simulator.mqtt_client import CoreMqttClient
from tools.simulator.utils import ALL_PROTOCOLS, Topics, generate_random_hex


class ReceiverConfig(BaseModel):
    id: str


class TransmitterConfig(BaseModel):
    id: str


class BridgeConfig(BaseModel):
    """Configuration for a simulated bridge."""

    bid: str
    bridge_type: str = "mqtt"  # "mqtt" or "serial"
    ip: str | None = None  # For MQTT bridges
    port: str | None = None  # For Serial bridges (e.g., "/dev/ttyUSB0")
    baudrate: int = 115200  # For Serial bridges
    protocols: list[str] = Field(default_factory=list)
    rx_count: int = 1
    tx_count: int = 1


class BridgeState(BaseModel):
    """Represents the state of a simulated bridge."""

    id: str
    bridge_type: str = "mqtt"  # "mqtt" or "serial"
    ip: str | None = None
    port: str | None = None
    name: str
    version: str = "1.0.0-sim"
    mac: str | None = None
    receivers: list[ReceiverConfig] = Field(default_factory=lambda: [ReceiverConfig(id="ir_rx_main")])
    transmitters: list[TransmitterConfig] = Field(default_factory=lambda: [TransmitterConfig(id="ir_tx_main")])
    capabilities: list[str] = Field(default_factory=list)
    enabled_protocols: list[str] = Field(default_factory=list)
    online: bool = False

    @property
    def rx(self) -> int:
        return len(self.receivers)

    @property
    def tx(self) -> int:
        return len(self.transmitters)


class SimulatorEngine:
    """
    Encapsulates all bridge simulation and state management.
    """

    def __init__(self, broker: str, port: int, on_log: Callable[[str, str, str], None], on_bridges_updated: Callable[[], None], config_file: str = "simulator_config.json"):
        self.broker = broker
        self.port = port
        self.on_log = on_log
        self.on_bridges_updated = on_bridges_updated

        self.bridges: list[BridgeState] = []
        self.clients: dict[str, CoreMqttClient] = {}
        self.serial_threads: dict[str, dict] = {}  # { bid: {"running": bool, "thread": Thread, "fd": int} }
        self.simulated_configs: list[BridgeConfig] = []
        self.is_running = False
        self.loopback_enabled = False
        # Per-bridge loopback matrix: {(tx_bid, tx_id): [(rx_bid, rx_id), ...]}
        self.loopback_routes: dict[tuple[str, str], list[tuple[str, str]]] = {}
        self.main_mqtt_client: CoreMqttClient | None = None
        self.config_file = config_file

        self.load_config()

    def set_main_client(self, client: CoreMqttClient):
        self.main_mqtt_client = client
        if client:
            self.is_running = True
            self.restart_bridges()

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file) as f:
                    data = json.load(f)
                    self.simulated_configs = [BridgeConfig(**item) for item in data]
                self.on_log("SIM", f"Loaded configuration for {len(self.simulated_configs)} bridges.", "INFO")
            except Exception as e:
                self.on_log("SIM", f"Failed to load config: {e}", "ERROR")

    def save_config(self):
        try:
            with open(self.config_file, "w") as f:
                data = [cfg.model_dump() for cfg in self.simulated_configs]
                json.dump(data, f, indent=2)
        except Exception as e:
            self.on_log("SIM", f"Failed to save config: {e}", "ERROR")

    def get_bridge_by_id(self, bid: str) -> BridgeState | None:
        return next((b for b in self.bridges if b.id == bid), None)

    def spawn_bridges(self, count: int, rx_count: int = 1, tx_count: int = 1):
        for _ in range(count):
            bid = f"sim-bridge-{uuid.uuid4().hex[:4]}"
            ip = f"192.168.1.{random.randint(100, 200)}"
            self.simulated_configs.append(BridgeConfig(bid=bid, bridge_type="mqtt", ip=ip, protocols=ALL_PROTOCOLS[:], rx_count=rx_count, tx_count=tx_count))
            self.add_bridge(bid)
        self.save_config()

    def spawn_serial_bridge(self, port: str, baudrate: int = 115200, rx_count: int = 1, tx_count: int = 1) -> str:
        """Create a new serial bridge simulator."""
        bid = f"sim-bridge-{uuid.uuid4().hex[:4]}"
        self.simulated_configs.append(BridgeConfig(bid=bid, bridge_type="serial", port=port, baudrate=baudrate, protocols=ALL_PROTOCOLS[:], rx_count=rx_count, tx_count=tx_count))
        self.add_bridge(bid)
        self.save_config()
        self.on_log("SIM", f"Created serial bridge {bid}", "INFO")
        return bid

    def restart_bridges(self):
        for cfg in self.simulated_configs:
            self.add_bridge(cfg.bid)

    def _generate_mac(self, bid: str) -> str:
        return ":".join(f"{random.randint(0, 255):02X}" for _ in range(6))

    def add_bridge(self, bid: str):
        """Add a bridge based on configuration stored in simulated_configs."""
        if self.get_bridge_by_id(bid) and (bid in self.clients or bid in self.serial_threads):
            return

        # Get the saved configuration for this bridge
        saved_cfg = next((c for c in self.simulated_configs if c.bid == bid), None)
        if not saved_cfg:
            return

        enabled_protocols = saved_cfg.protocols if saved_cfg else ALL_PROTOCOLS[:]

        existing_bridge = self.get_bridge_by_id(bid)
        if existing_bridge:
            # Update existing bridge
            existing_bridge.bridge_type = saved_cfg.bridge_type
            existing_bridge.ip = saved_cfg.ip
            existing_bridge.port = saved_cfg.port
            existing_bridge.enabled_protocols = enabled_protocols
        else:
            # Create new bridge with proper capabilities
            receivers = [ReceiverConfig(id=f"ir_rx_{i}") for i in range(max(1, saved_cfg.rx_count))]
            transmitters = [TransmitterConfig(id=f"ir_tx_{i}") for i in range(max(1, saved_cfg.tx_count))]
            mac = self._generate_mac(bid)

            new_bridge = BridgeState(
                id=bid,
                bridge_type=saved_cfg.bridge_type,
                ip=saved_cfg.ip,
                port=saved_cfg.port,
                name=f"Simulated Bridge {bid.split('-')[-1]}",
                mac=mac,
                receivers=receivers,
                transmitters=transmitters,
                capabilities=ALL_PROTOCOLS[:],
                enabled_protocols=enabled_protocols,
                online=False,
            )
            self.bridges.append(new_bridge)

        self.on_bridges_updated()
        bridge = self.get_bridge_by_id(bid)

        if bridge.bridge_type == "mqtt":
            self._start_mqtt_bridge(bid, bridge)
        elif bridge.bridge_type == "serial":
            self._start_serial_bridge(bid, bridge)

    def _start_mqtt_bridge(self, bid: str, bridge: BridgeState):
        """Start an MQTT bridge simulator."""
        state_topic = Topics.bridge_state(bid)
        lwt_payload = json.dumps({"online": False})

        client = CoreMqttClient(self.broker, self.port, will_topic=state_topic, will_payload=lwt_payload, bid=bid, on_log=self.on_log)
        self.clients[bid] = client

        config_topic = Topics.bridge_config(bid)
        config_payload = {
            "id": bridge.id,
            "name": bridge.name,
            "ip": bridge.ip,
            "mac": bridge.mac,
            "version": bridge.version,
            "receivers": [r.model_dump() for r in bridge.receivers],
            "transmitters": [t.model_dump() for t in bridge.transmitters],
            "capabilities": bridge.capabilities,
        }
        client.queue_publish(config_topic, json.dumps(config_payload), True)

        state_payload = {"online": True, "enabled_protocols": bridge.enabled_protocols}
        client.queue_publish(state_topic, json.dumps(state_payload), True)

        client.start()

    def _start_serial_bridge(self, bid: str, bridge: BridgeState):
        """Start a Serial bridge simulator using PTY."""
        if not PTY_SUPPORTED:
            self.on_log("SIM", f"PTY not supported on this platform. Serial bridge {bid} is a dummy.", "WARN")
            bridge.online = True
            return

        try:
            master, slave = pty.openpty()
            port_name = os.ttyname(slave)

            # Set slave to raw mode
            attr = termios.tcgetattr(slave)
            attr[3] = attr[3] & ~termios.ECHO  # Disable echo
            termios.tcsetattr(slave, termios.TCSANOW, attr)

            bridge.port = port_name
            bridge.online = True
            self.on_bridges_updated()

            thread_ctx = {
                "running": True,
                "fd": master,
                "slave": slave,
            }

            config_payload = {
                "type": "config",
                "id": bridge.id,
                "name": bridge.name,
                "mac": bridge.mac,
                "version": bridge.version,
                "receivers": [r.model_dump() for r in bridge.receivers],
                "transmitters": [t.model_dump() for t in bridge.transmitters],
                "capabilities": bridge.capabilities,
            }
            state_payload = {"type": "state", "online": True, "enabled_protocols": bridge.enabled_protocols}

            def _run(b=bid, br=bridge, ctx=thread_ctx, cp=config_payload, sp=state_payload):
                # Write initial handshake inside the thread so a full PTY buffer
                # (when nobody reads the slave end, e.g. in tests) never blocks
                # the main thread.
                self._serial_write(b, cp)
                self._serial_write(b, sp)
                self._serial_read_loop(b, br, ctx)

            t = threading.Thread(target=_run, daemon=True)
            thread_ctx["thread"] = t
            self.serial_threads[bid] = thread_ctx
            t.start()

            self.on_log("SIM", f"Serial bridge {bid} started on {port_name}", "INFO")

        except Exception as e:
            self.on_log("SIM", f"Failed to start serial bridge {bid}: {e}", "ERROR")

    def _serial_read_loop(self, bid: str, bridge: BridgeState, ctx: dict):
        import select

        buffer = ""
        while ctx.get("running"):
            try:
                # Use select with a timeout so we can check ctx["running"] periodically
                r, _, _ = select.select([ctx["fd"]], [], [], 0.5)
                if r:
                    data = os.read(ctx["fd"], 1024)
                    if not data:
                        break
                    buffer += data.decode("utf-8", errors="ignore")

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line:
                            self._process_command(bid, line)
            except Exception as e:
                if ctx.get("running"):
                    self.on_log("SIM", f"Serial read error for {bid}: {e}", "ERROR")
                break

    def _serial_write(self, bid: str, payload: dict):
        if bid in self.serial_threads:
            try:
                data = json.dumps(payload) + "\n"
                os.write(self.serial_threads[bid]["fd"], data.encode("utf-8"))
            except Exception as e:
                self.on_log("SIM", f"Serial write error for {bid}: {e}", "ERROR")

    def delete_bridge(self, bid: str):
        self.simulated_configs = [c for c in self.simulated_configs if c.bid != bid]
        self.save_config()
        self.bridges = [b for b in self.bridges if b.id != bid]

        if bid in self.clients:
            client = self.clients.pop(bid)
            topics = [
                Topics.bridge_config(bid),
                Topics.bridge_state(bid),
                Topics.bridge_command(bid),
                Topics.bridge_response(bid),
                Topics.bridge_received(bid),
                Topics.bridge_root(bid),
            ]

            if self.main_mqtt_client and self.main_mqtt_client.is_connected():
                for topic in topics:
                    self.main_mqtt_client.publish(topic, "", retain=True)
            else:
                for topic in topics:
                    client.publish(topic, "", retain=True)
                threading.Timer(0.2, client.stop).start()

            if self.main_mqtt_client and self.main_mqtt_client.is_connected():
                try:
                    client.client.disconnect()
                except Exception:
                    pass
                client.stop()

        if bid in self.serial_threads:
            ctx = self.serial_threads.pop(bid)
            ctx["running"] = False
            try:
                os.close(ctx["fd"])
                os.close(ctx["slave"])
            except Exception:
                pass

        self.on_bridges_updated()

    def delete_all_bridges(self):
        for bridge in list(self.bridges):
            self.delete_bridge(bridge.id)

    def rename_bridge(self, bid: str, new_name: str):
        bridge = self.get_bridge_by_id(bid)
        if not bridge:
            return
        bridge.name = new_name
        self.on_bridges_updated()

        if bridge.bridge_type == "mqtt" and bid in self.clients:
            config_topic = Topics.bridge_config(bid)
            config_payload = {
                "id": bridge.id,
                "name": bridge.name,
                "ip": bridge.ip,
                "mac": bridge.mac,
                "version": bridge.version,
                "receivers": [r.model_dump() for r in bridge.receivers],
                "transmitters": [t.model_dump() for t in bridge.transmitters],
                "capabilities": bridge.capabilities,
            }
            self.clients[bid].publish(config_topic, json.dumps(config_payload), True)

    def update_protocols(self, bid: str, protocols: list[str]):
        bridge = self.get_bridge_by_id(bid)
        if not bridge:
            return

        bridge.enabled_protocols = protocols

        for cfg in self.simulated_configs:
            if cfg.bid == bid:
                cfg.protocols = protocols
                break
        self.save_config()

        if bridge.bridge_type == "mqtt" and bid in self.clients:
            self.clients[bid].publish(Topics.bridge_state(bid), json.dumps({"online": True, "enabled_protocols": protocols}), retain=True)
        elif bridge.bridge_type == "serial" and bid in self.serial_threads:
            self._serial_write(bid, {"type": "state", "online": True, "enabled_protocols": protocols})

        self.on_bridges_updated()

    def handle_message(self, topic: str, payload: str, retained: bool = False):
        if not self.is_running:
            return
        parts = topic.split("/")
        if len(parts) < 4 or parts[0] != "ir2mqtt" or parts[1] != "bridge":
            return

        bid, msg_type = parts[2], parts[3]

        if msg_type in ("config", "state"):
            bridge = self.get_bridge_by_id(bid)
            if not bridge:
                self.on_log("SIM", f"Discovered existing bridge via retained message: {bid}", "INFO")
                # Create a minimal bridge state if discovered via MQTT but not in config
                bridge = BridgeState(id=bid, name=f"Discovered {bid}", bridge_type="mqtt")
                self.bridges.append(bridge)

            if not payload:
                self.bridges = [b for b in self.bridges if b.id != bid]
                self.on_bridges_updated()
                return

            try:
                data = json.loads(payload)
                # Update fields if present in payload
                for field in ["name", "ip", "mac", "online", "enabled_protocols", "bridge_type", "capabilities", "receivers", "transmitters"]:
                    if field in data:
                        if field == "receivers":
                            bridge.receivers = [ReceiverConfig(**r) if isinstance(r, dict) else r for r in data[field]]
                        elif field == "transmitters":
                            bridge.transmitters = [TransmitterConfig(**t) if isinstance(t, dict) else t for t in data[field]]
                        else:
                            setattr(bridge, field, data[field])
                self.on_bridges_updated()
            except (json.JSONDecodeError, ValueError):
                self.on_log("SIM", f"Could not decode JSON for {topic}", "ERROR")
            return

        if bid not in self.clients:
            return

        if msg_type == "command":
            self._process_command(bid, payload)

    def _process_command(self, bid: str, payload: str):
        try:
            data = json.loads(payload)
            command = data.get("command")

            if command == "get_config":
                bridge = self.get_bridge_by_id(bid)
                if bridge:
                    config_payload = {
                        "type": "config",
                        "id": bridge.id,
                        "name": bridge.name,
                        "mac": bridge.mac,
                        "version": bridge.version,
                        "receivers": [r.model_dump() for r in bridge.receivers],
                        "transmitters": [t.model_dump() for t in bridge.transmitters],
                        "capabilities": bridge.capabilities,
                    }
                    if "request_id" in data:
                        config_payload["request_id"] = data["request_id"]
                        config_payload["success"] = True
                    self._send_response(bid, config_payload)

            elif command == "ping":
                if "request_id" in data:
                    self._send_response(bid, {"type": "response", "request_id": data["request_id"], "success": True})

            elif command == "set_protocols":
                new_protocols = data.get("protocols", [])
                self.update_protocols(bid, new_protocols)

                if "request_id" in data:
                    self._send_response(bid, {"type": "response", "request_id": data["request_id"], "success": True})

            elif command == "send":
                transmitter_id = data.get("transmitter_id")
                # transmitter_id may be a list (multi-channel) or a single string
                tx_ids: list[str] = []
                if isinstance(transmitter_id, list):
                    tx_ids = transmitter_id
                elif isinstance(transmitter_id, str):
                    tx_ids = [transmitter_id]

                self.on_log("SIM", f"Bridge {bid} received 'send' command for transmitter(s) {tx_ids or 'any'}.", "DEBUG")

                if "request_id" in data:
                    self._send_response(bid, {"type": "response", "request_id": data["request_id"], "success": True})

                if "code" in data:
                    code = data["code"]
                    if code.get("protocol") == "raw" and "frequency" not in code:
                        code["frequency"] = 38000

                    # Global loopback: echo back on the same bridge
                    if self.loopback_enabled:
                        self.on_log("SIM", f"Global loopback: echoing code for {bid}.", "INFO")
                        self.inject_signal(bid, code)

                    # Per-bridge loopback matrix routing
                    effective_tx_ids = tx_ids if tx_ids else [t.id for t in (self.get_bridge_by_id(bid).transmitters if self.get_bridge_by_id(bid) else [])]
                    for tx_id in effective_tx_ids:
                        targets = self.loopback_routes.get((bid, tx_id), [])
                        for rx_bid, rx_id in targets:
                            self.on_log("SIM", f"Loopback matrix: {bid}/{tx_id} → {rx_bid}/{rx_id}", "INFO")
                            signal = code.copy()
                            signal["receiver_id"] = rx_id
                            self.inject_signal(rx_bid, signal)

        except Exception as e:
            self.on_log("SIM", f"Error processing command for {bid}: {e}", "ERROR")

    def set_loopback_route(self, tx_bid: str, tx_id: str, rx_bid: str, rx_id: str, enabled: bool):
        """Enable or disable a loopback route from a TX channel to an RX channel."""
        key = (tx_bid, tx_id)
        target = (rx_bid, rx_id)
        if enabled:
            if key not in self.loopback_routes:
                self.loopback_routes[key] = []
            if target not in self.loopback_routes[key]:
                self.loopback_routes[key].append(target)
        else:
            if key in self.loopback_routes:
                self.loopback_routes[key] = [t for t in self.loopback_routes[key] if t != target]

    def get_loopback_route(self, tx_bid: str, tx_id: str, rx_bid: str, rx_id: str) -> bool:
        """Check if a loopback route is active."""
        return (rx_bid, rx_id) in self.loopback_routes.get((tx_bid, tx_id), [])

    def _send_response(self, bid: str, payload: dict):
        bridge = self.get_bridge_by_id(bid)
        if not bridge:
            return
        if bridge.bridge_type == "mqtt" and bid in self.clients:
            self.clients[bid].publish(Topics.bridge_response(bid), json.dumps(payload))
        elif bridge.bridge_type == "serial":
            self._serial_write(bid, payload)

    def inject_signal(self, bid: str, payload: dict):
        bridge = self.get_bridge_by_id(bid)
        if not bridge:
            return

        # Add receiver_id if missing
        if "receiver_id" not in payload and bridge.receivers:
            payload["receiver_id"] = bridge.receivers[0].id

        # Add frequency if raw and missing
        if payload.get("protocol") == "raw" and "frequency" not in payload:
            payload["frequency"] = 38000

        if bridge.bridge_type == "mqtt" and bid in self.clients:
            self.clients[bid].publish(Topics.bridge_received(bid), json.dumps(payload))
        elif bridge.bridge_type == "serial":
            self._serial_write(bid, {"type": "received", **payload})

    def inject_random_nec(self, bid: str):
        payload = {"protocol": "nec", "payload": {"address": generate_random_hex(1), "command": generate_random_hex(1)}}
        self.inject_signal(bid, payload)

    def stop_simulation(self):
        self.is_running = False
        for bid, client in self.clients.items():
            if client.is_connected():
                client.publish(Topics.bridge_state(bid), json.dumps({"online": False}), retain=True)
        if self.clients:
            time.sleep(0.1)
        for client in self.clients.values():
            try:
                client.client.disconnect()
            except Exception:
                pass
            client.stop()

        for bid, ctx in self.serial_threads.items():
            ctx["running"] = False
            try:
                os.close(ctx["fd"])
                os.close(ctx["slave"])
            except Exception:
                pass

    def clear_data(self):
        self.clients.clear()
        self.serial_threads.clear()
        self.bridges.clear()
        self.on_bridges_updated()

    def shutdown(self):
        self.stop_simulation()
        self.clear_data()
