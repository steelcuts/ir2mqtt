import argparse
import asyncio
import os
import shlex
import sys
import time

# --- CONSTANTS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT, "data")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from simulator_core import ALL_PROTOCOLS, CoreMqttClient, DeviceController, SimulatorEngine  # noqa: E402

from tools.simulator.utils import Topics  # noqa: E402


def print_help():
    """Prints the help message for all commands."""
    print("\n--- CLI COMMANDS ---")
    print("  help                               - Shows this help")
    print("  list                               - Lists active bridges, devices & automations")
    print("  spawn [mqtt|serial] <count>        - Creates new bridges (default: 1 mqtt)")
    print("  delete <bid|index|all>             - Deletes a bridge by ID, index, or 'all'")
    print("  protocols <bid|index> [list|enable|disable] - Manage enabled protocols for a bridge")
    print("  logs <on|off>                      - Toggles background logs on or off")
    print("\n--- CONTROL ---")
    print('  simpress <bid|index> "<dev>" "<btn>" [rx] - Simulates a real remote press (bridge receives IR code)')
    print('                                              Ex: simpress 1 "Living Room TV" "Power" ir_rx_main')
    print("  tx_test <bid|index> <tx_id>               - Tests a specific transmitter on the bridge")
    print('  hacmd "<dev>" "<btn>"                     - Sends Home Assistant Command (Backend)')
    print('  sacmd "<dev>" "<btn>"                     - Sends Standalone Command (Backend)')
    print('  trigger "<auto_name>"                     - Triggers an automation')
    print("  quit / exit                               - Exits the simulator\n")


class SimulatorCLI:
    """Encapsulates the CLI logic and state."""

    def __init__(self, engine: SimulatorEngine, controller: DeviceController, mqtt: CoreMqttClient):
        self.engine = engine
        self.controller = controller
        self.mqtt = mqtt
        self.show_logs = False
        self.commands = {
            "help": self._handle_help,
            "list": self._handle_list,
            "spawn": self._handle_spawn,
            "delete": self._handle_delete,
            "protocols": self._handle_protocols,
            "logs": self._handle_logs,
            "simpress": self._handle_simpress,
            "tx_test": self._handle_tx_test,
            "hacmd": self._handle_command,
            "sacmd": self._handle_command,
            "trigger": self._handle_trigger,
        }

    def _console_logger(self, source: str, message: str, level: str):
        if not self.show_logs:
            return
        color_map = {
            "INFO": "\033[92m",  # Green
            "WARN": "\033[93m",  # Yellow
            "ERROR": "\033[91m",  # Red
            "DEBUG": "\033[94m",  # Blue
            "CTRL": "\033[95m",  # Magenta for Controller
        }
        reset = "\033[0m"
        color = color_map.get(level, reset)
        print(f"\r{color}[{level}] [{source}]{reset} {message}\n> ", end="")

    def on_main_client_connection_change(self, status: bool, err: str | None):
        """Callback to show the main client's connection status."""
        if status:
            self._console_logger("MQTT", "Main client successfully connected.", "INFO")
        else:
            msg = f"Main client disconnected. {err or ''}".strip()
            self._console_logger("MQTT", msg, "WARN")

    def _resolve_bridge_id(self, target: str) -> str | None:
        """Resolves a bridge ID from an ID string or a list index."""
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(self.engine.bridges):
                return self.engine.bridges[idx].id

        if self.engine.get_bridge_by_id(target):
            return target

        return None

    def _handle_help(self, _parts):
        print_help()

    def _handle_logs(self, parts):
        self.show_logs = len(parts) > 1 and parts[1].lower() in ["on", "1", "true"]
        print(f"Logs: {'ON' if self.show_logs else 'OFF'}")

    def _handle_list(self, _parts):
        print(f"\nBridges ({len(self.engine.bridges)}):")
        for i, b in enumerate(self.engine.bridges):
            bridge_type = f"{b.bridge_type.upper()}"
            if b.ip:
                bridge_type += f" ({b.ip})"
            elif b.port:
                bridge_type += f" ({b.port})"
            rx_tx = f" [RX:{b.rx}, TX:{b.tx}]"
            status = "Online" if b.online else "Offline"
            print(f" {i + 1}. {b.name} ({b.id}) {bridge_type}{rx_tx} [{status}]")
        print(f"Devices ({len(self.controller.devices)}):")
        for d in self.controller.devices:
            if d:
                print(f" - {d.name}")
        print(f"Automations ({len(self.controller.automations)}):")
        for a in self.controller.automations:
            print(f" - {a.name}")
        print()

    def _handle_spawn(self, parts):
        bridge_type = "mqtt"
        count = 1

        if len(parts) > 1:
            if parts[1].lower() in ["mqtt", "serial"]:
                bridge_type = parts[1].lower()
                if len(parts) > 2 and parts[2].isdigit():
                    count = int(parts[2])
            elif parts[1].isdigit():
                count = int(parts[1])

        if bridge_type == "mqtt":
            self.engine.spawn_bridges(count)
        else:
            for _ in range(count):
                self.engine.spawn_serial_bridge("auto")

        print(f"{count} {bridge_type.upper()} bridge(s) spawned.\n")

    def _handle_delete(self, parts):
        if len(parts) < 2:
            print("Usage: delete <bridge_id_or_index|all>\n")
            return

        target = parts[1]
        if target.lower() == "all":
            self.engine.delete_all_bridges()
            print("All bridges deleted.\n")
            return

        bid = self._resolve_bridge_id(target)

        if bid:
            self.engine.delete_bridge(bid)
            print(f"Bridge {bid} deleted.\n")
        else:
            print(f"Error: Bridge '{target}' not found.\n")

    def _handle_protocols(self, parts):
        if len(parts) < 2:
            print("Usage: protocols <bid|index> [list|enable|disable] [protocol]\n")
            return

        target = parts[1]
        bid = self._resolve_bridge_id(target)
        if not bid:
            print(f"Error: Bridge '{target}' not found.\n")
            return

        bridge = self.engine.get_bridge_by_id(bid)

        action = parts[2].lower() if len(parts) > 2 else "list"

        if action == "list":
            print(f"Protocols for {bid}:")
            for p in ALL_PROTOCOLS:
                status = "[x]" if p in bridge.enabled_protocols else "[ ]"
                print(f" {status} {p}")
            print()
            return

        if len(parts) < 4:
            print(f"Usage: protocols <bid|index> {action} <protocol>\n")
            return

        proto = parts[3].lower()
        if proto not in ALL_PROTOCOLS:
            print(f"Error: Unknown protocol '{proto}'. Available: {', '.join(ALL_PROTOCOLS)}\n")
            return

        current = set(bridge.enabled_protocols)

        if action == "enable":
            current.add(proto)
        elif action == "disable":
            current.discard(proto)

        self.engine.update_protocols(bid, list(current))
        print(f"Protocol '{proto}' {action}d for {bid}.\n")

    def _handle_simpress(self, parts):
        if len(parts) < 4:
            print('Usage: simpress <bid|index> "Device Name" "Button Name" [receiver_id]\n')
            return
        target, dev_name, btn_name = parts[1], parts[2], parts[3]
        receiver_id = parts[4] if len(parts) > 4 else None

        bid = self._resolve_bridge_id(target)
        if not bid:
            print(f"Error: Bridge '{target}' not found.\n")
            return

        _dev, btn = self.controller.find_device_and_button(dev_name, btn_name)

        if btn and btn.code:
            payload = btn.code.model_dump(exclude_none=True)
            if receiver_id:
                payload["receiver_id"] = receiver_id
            self.engine.inject_signal(bid, payload)
            print(f"Simulating press on '{dev_name} -> {btn_name}' via bridge {bid} (RX: {receiver_id or 'default'})\n")
        else:
            print(f"Error: Button '{btn_name}' in device '{dev_name}' not found or has no code.\n")

    def _handle_tx_test(self, parts):
        if len(parts) < 3:
            print("Usage: tx_test <bid|index> <transmitter_id>\n")
            return
        target, tx_id = parts[1], parts[2]
        bid = self._resolve_bridge_id(target)
        if not bid:
            print(f"Error: Bridge '{target}' not found.\n")
            return

        payload = {"command": "send", "request_id": "cli-test", "transmitter_id": tx_id, "code": {"protocol": "nec", "payload": {"address": "0x1234", "command": "0x5678"}}}
        import json

        bridge = self.engine.get_bridge_by_id(bid)
        if bridge and bridge.bridge_type == "mqtt":
            self.engine.clients[bid].publish(Topics.bridge_command(bid), json.dumps(payload))
        elif bridge and bridge.bridge_type == "serial":
            self.engine._serial_write(bid, payload)

        print(f"Sent test command to bridge {bid} for transmitter '{tx_id}'.\n")

    def _handle_command(self, parts):
        cmd, dev_name, btn_name = parts[0], parts[1], parts[2]
        if len(parts) < 3:
            print(f'Usage: {cmd} "Device Name" "Button Name"\n')
            return

        dev, btn = self.controller.find_device_and_button(dev_name, btn_name)

        if not dev or not btn:
            print("Error: Device or button not found.\n")
            return

        if cmd == "hacmd":
            topic = Topics.cmd_ha(dev.id, btn.id)
        else:  # sacmd
            topic = Topics.cmd_sa(dev.name, btn.name)

        self.mqtt.publish(topic, "PRESS")
        print(f"MQTT command sent to: {topic}\n")

    def _handle_trigger(self, parts):
        if len(parts) < 2:
            print('Usage: trigger "Automation Name"\n')
            return
        auto_name = parts[1]
        auto = self.controller.find_automation(auto_name)

        if auto:
            topic = Topics.automation_trigger_name(auto.name)
            self.mqtt.publish(topic, "PRESS")
            print(f"Automation '{auto.name}' triggered.\n")
        else:
            print("Error: Automation not found.\n")

    def run(self):
        """Starts the interactive command loop."""
        print_help()
        while True:
            try:
                cmd_line = input("> ").strip()
                if not cmd_line:
                    continue

                parts = shlex.split(cmd_line)
                cmd = parts[0].lower()

                if cmd in ["quit", "exit"]:
                    break

                handler = self.commands.get(cmd)
                if handler:
                    handler(parts)
                else:
                    print(f"Unknown command: {cmd}. Type 'help' for an overview.\n")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error during execution: {e}\n")


def main():
    parser = argparse.ArgumentParser(description="IR2MQTT Simulator CLI")
    parser.add_argument("--broker", default="localhost", help="MQTT Broker IP")
    parser.add_argument("--port", type=int, default=1883, help="MQTT Broker Port")
    parser.add_argument("--data", default=DEFAULT_DATA_DIR, help="Path to the data directory")
    parser.add_argument("--clean", action="store_true", help="Clear existing bridge configuration on startup")
    args = parser.parse_args()

    print(f"Starting IR2MQTT Simulator CLI (Broker: {args.broker}:{args.port})")

    if args.clean:
        config_path = "simulator_config.json"
        if os.path.exists(config_path):
            try:
                os.remove(config_path)
                print("Cleared existing simulator configuration.")
            except OSError as e:
                print(f"Error clearing configuration: {e}")

    # The CLI class will manage its own logger
    # We need to instantiate it early to get its logger method
    # But the engine and controller need to be created first.
    # This creates a bit of a dependency loop.
    # Solution: We can set the logger on the components after instantiation.

    # This is a placeholder for the CLI instance.
    cli_instance = [None]

    def log_wrapper(source, message, level):
        if cli_instance[0]:
            cli_instance[0]._console_logger(source, message, level)

    def conn_change_wrapper(status, err):
        if cli_instance[0]:
            cli_instance[0].on_main_client_connection_change(status, err)

    # Initialize Engine & Controller
    engine = SimulatorEngine(args.broker, args.port, on_log=log_wrapper, on_bridges_updated=lambda: None)
    if engine.simulated_configs:
        print(f"Loaded configuration for {len(engine.simulated_configs)} bridges.")
    controller = DeviceController(on_log=log_wrapper)

    # Load Project Data
    try:
        print(f"Loading data from SQLite in: {args.data}")
        asyncio.run(controller.load_data(args.data))
        print(f"Loaded {len(controller.devices)} devices and {len(controller.automations)} automations.")
    except Exception as e:
        print(f"Failed to load data from database: {e}")

    main_client = CoreMqttClient(
        broker=args.broker,
        port=args.port,
        on_log=log_wrapper,
        on_message=engine.handle_message,
        on_connection_change=conn_change_wrapper,
    )

    # Now create the CLI instance and link it all up
    cli = SimulatorCLI(engine, controller, main_client)
    cli_instance[0] = cli  # Set the instance for the wrappers to use

    engine.set_main_client(main_client)
    main_client.start()
    time.sleep(0.5)

    cli.run()

    print("\nExiting simulator...")
    engine.shutdown()
    main_client.stop()


if __name__ == "__main__":
    main()
