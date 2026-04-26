# IR2MQTT Simulator

A simulator for ir2mqtt bridges. Spawn virtual MQTT or Serial bridges that behave like real hardware — useful for development and testing without a physical device.

Both a GUI and a CLI are available.

## Dependencies

Requires Python 3 and the packages listed in `requirements.txt`:

```
PyQt6, paho-mqtt, sqlalchemy, aiosqlite, pydantic, pydantic-settings
```

These are installed automatically by the startup scripts.

## How to Run

### GUI

**Linux / macOS:**
```bash
./run_gui.sh
```

**Windows:**
```cmd
run_gui.bat
```

### CLI

**Linux / macOS:**
```bash
./run_cli.sh [options]
```

**Windows:**
```cmd
run_cli.bat [options]
```

#### CLI Arguments

| Argument | Default | Description |
|---|---|---|
| `--broker <ip>` | `localhost` | MQTT broker IP |
| `--port <port>` | `1883` | MQTT broker port |
| `--data <path>` | `../../data` | Path to the data directory (SQLite database) |
| `--clean` | — | Clear saved bridge configuration on startup |

## CLI Commands

Once running, the following commands are available:

### Bridge Management

| Command | Description |
|---|---|
| `list` | List all active bridges, devices, and automations |
| `spawn [mqtt\|serial] [count]` | Spawn virtual bridges (default: 1 MQTT) |
| `delete <id\|index\|all>` | Delete a bridge by ID, list index, or all |
| `protocols <id\|index> list` | List protocols and their enabled state |
| `protocols <id\|index> enable <protocol>` | Enable a protocol on a bridge |
| `protocols <id\|index> disable <protocol>` | Disable a protocol on a bridge |
| `logs <on\|off>` | Toggle background MQTT log output |

### Simulation & Control

| Command | Description |
|---|---|
| `simpress <id\|index> "Device" "Button" [rx_id]` | Simulate a remote press — the bridge receives the button's IR code |
| `tx_test <id\|index> <transmitter_id>` | Send a test NEC command to a specific transmitter |
| `hacmd "Device" "Button"` | Send a Home Assistant MQTT command |
| `sacmd "Device" "Button"` | Send a Standalone MQTT command |
| `trigger "Automation Name"` | Trigger an automation by name |
| `help` | Show command reference |
| `quit` / `exit` | Exit the simulator |

#### Examples

```
spawn mqtt 2
spawn serial
simpress 1 "Living Room TV" "Power"
simpress 1 "Living Room TV" "Power" ir_rx_main
protocols 1 list
protocols 1 disable nec
hacmd "Living Room TV" "Power"
trigger "Turn off all lights"
delete all
```

> Bridges can be referenced by their list index (e.g. `1`) or their full bridge ID.
