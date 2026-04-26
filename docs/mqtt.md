# MQTT Topic Reference

This section details the MQTT topics used by IR2MQTT. This is useful for debugging, manual integration, or using the application in standalone mode.

## Standalone Mode
In standalone mode, topics use readable names (e.g. `living_room_tv`) or IDs depending on your settings.

### Subscriptions (Input)
- `ir2mqtt/devices/{device}/{button}/in`: Send `PRESS` to trigger a button.
- `ir2mqtt/automations/{automation}/trigger`: Send `PRESS` to trigger an automation.

### Publications (Output)
- `ir2mqtt/devices/{device}/last_button`: Name of the last received button.
- `ir2mqtt/devices/{device}/{button}/out`: State (`ON`/`OFF`) for input buttons.
- `ir2mqtt/devices/{device}/{button}/event`: Published when an event button is received.
- `ir2mqtt/automations/{automation}/state`: State (`ON`/`OFF`) of an automation.
- `ir2mqtt/automations/{automation}/event`: JSON payload when an automation fires an event.

## Home Assistant Mode
In this mode, topics use internal IDs to ensure stability.

### Subscriptions (Input)
- `ir2mqtt/cmd/{device_id}/{button_id}`: Send `PRESS` to trigger a button.
- `ir2mqtt/automation/{automation_id}/trigger`: Send `PRESS` to trigger an automation.

### Publications (Output)
- `ir2mqtt/status/{device_id}/last_button`: Name of the last received button.
- `ir2mqtt/events/{device_id}`: Payload is the button name. Used for HA device triggers.
- `ir2mqtt/input/{device_id}/{button_id}/state`: State (`ON`/`OFF`) for binary sensors.
- `ir2mqtt/automation/{automation_id}/state`: State (`ON`/`OFF`) of an automation.
- `ir2mqtt/automation_event/{automation_id}/{event}/state`: Payload `press` when an automation fires an HA event.

## Bridge Communication

The bridge firmware communicates with the backend using newline-delimited JSON over MQTT (or UART in serial mode). The **MQTT base topic** is `ir2mqtt/bridge/<device_id>`.

| Topic | Direction | Retained | Description |
|-------|-----------|----------|-------------|
| `.../config` | Bridge → Host | Yes | Static configuration, published on boot or `get_config`. |
| `.../state` | Bridge → Host | Yes | Dynamic state (online status, enabled protocols). LWT sets `{"online": false}`. |
| `.../received` | Bridge → Host | No | IR signal received by the bridge. |
| `.../command` | Host → Bridge | No | Commands sent to the bridge (`send`, `set_protocols`, etc.). |
| `.../response` | Bridge → Host | No | Response to commands that include a `request_id`. |

### Bridge → Host Messages

#### Discovery (`/config`) — retained

Sent on boot, MQTT reconnect, or when `get_config` is received.

```json
{
  "type": "config",
  "id": "28562f9056c4",
  "name": "ir2mqtt-bridge-lan",
  "version": "2024.6.0",
  "mac": "28:56:2F:90:56:C4",
  "ip": "192.168.1.50",
  "network_type": "ethernet",
  "receivers": [{ "id": "rx1" }],
  "transmitters": [{ "id": "tx1" }],
  "capabilities": ["nec", "samsung", "raw"],
  "enabled_protocols": ["nec", "samsung"]
}
```

`ip` and `network_type` are omitted in serial-only mode.

#### State (`/state`) — retained

Sent on boot or when enabled protocols change. The broker publishes `{"online": false}` as the LWT on unexpected disconnect.

```json
{
  "type": "state",
  "request_id": "12345",
  "online": true,
  "enabled_protocols": ["nec", "samsung", "raw"]
}
```

#### Received IR (`/received`)

Fired when a signal is decoded by an active protocol. All protocol-specific data is in the `payload` object.

```json
{
  "type": "received",
  "protocol": "nec",
  "receiver_id": "rx1",
  "timestamp": 123456,
  "payload": {
    "address": "0xFF00",
    "command": "0x1A"
  }
}
```

Unmatched signals are decoded as `raw`:

```json
{
  "type": "received",
  "protocol": "raw",
  "receiver_id": "rx1",
  "timestamp": 123500,
  "payload": {
    "timings": [8976, -2239, 609, -1000]
  }
}
```

### Host → Bridge Commands (`/command`)

All commands accept an optional `"request_id"` field. If present, the bridge replies with `{"request_id": "...", "success": true/false}` on `/response`.

#### Send IR

`transmitter_id` can be a string, an array, or omitted (broadcasts to all transmitters).

```json
{
  "command": "send",
  "transmitter_id": "tx1",
  "code": {
    "protocol": "nec",
    "payload": {
      "address": "0xFF00",
      "command": "0x1A",
      "repeats": 1
    }
  }
}
```

RAW send (`frequency` defaults to `38000` if omitted):

```json
{
  "command": "send",
  "code": {
    "protocol": "raw",
    "payload": {
      "frequency": 38000,
      "timings": [8976, -2239, 609, -1000]
    }
  }
}
```

#### Set Active Protocols

Changes are persisted to flash on the bridge.

```json
{ "command": "set_protocols", "protocols": ["nec", "samsung", "raw"] }
```

#### Status Commands

| Command | Effect |
|---------|--------|
| `{"command": "get_state"}` or `{"command": "ping"}` | Re-publishes `/state` |
| `{"command": "get_config"}` | Re-publishes `/config` |

### Protocol Payload Reference

All fields below go inside the `"payload"` object when sending, and are returned inside `"payload"` in a `received` message.

| Protocol | Field | Type | Notes |
|----------|-------|------|-------|
| **nec** | `address`, `command` | 0xHEX / int | 16-bit address and command. |
| | `repeats` | int | Optional, default 0. |
| **samsung** | `data` | 0xHEX / int64 | 64-bit data packet. |
| | `nbits` | int | Optional, default 32. |
| **samsung36** | `address`, `command` | 0xHEX / int | 16-bit address, 32-bit command. |
| **sony** | `data` | 0xHEX / int | 32-bit data. |
| | `nbits` | int | Optional, default 12. |
| **panasonic** | `address`, `command` | 0xHEX / int | 16-bit address, 32-bit command. |
| **rc5** | `address`, `command` | 0xHEX / int | 8-bit address and command. |
| **rc6** | `address`, `command` | 0xHEX / int | 8-bit fields. |
| | `mode`, `toggle` | int | Optional, default 0. |
| **jvc** | `data` | 0xHEX / int | 32-bit data. |
| **lg** | `data` | 0xHEX / int | 32-bit data. |
| | `nbits` | int | Optional, default 28. |
| **coolix** | `first`, `second` | 0xHEX / int | Two 24-bit codes. |
| **pioneer** | `rc_code_1`, `rc_code_2` | 0xHEX / int | Two 16-bit codes. |
| **dish** | `address`, `command` | 0xHEX / int | 8-bit address and command. |
| **midea** | `data` | array | Array of 0xHEX or integers (bytes). |
| **haier** | `data` | array | Array of 0xHEX or integers (bytes). |
| **raw** | `timings` | array | Array of signed integers (µs). |
| | `frequency` | int | Optional, default 38000. |
| **pronto** | `data` | string | Send only. Hex string format. |
| | `delta` | int | Optional, default 0. |
| **aeha** | `address` | 0xHEX | 16-bit address. |
| | `data` | array | Byte array. |
| **abbwelcome** | `address`, `command` | 0xHEX / int | 32-bit source address, 8-bit message type. |
| **beo4** | `command` | 0xHEX / int | 8-bit command. |
| | `source` | 0xHEX / int | Optional. |
| **byronsx** | `address`, `command` | 0xHEX / int | 8-bit address and command. |
| **canalsat** | `device`, `command` | 0xHEX / int | 8-bit fields. `address` optional. |
| **canalsat_ld** | `device`, `command` | 0xHEX / int | 8-bit fields. `address` optional. |
| **dooya** | `address`, `command` | 0xHEX / int | 32-bit motor ID, 8-bit button code. `channel` optional. |
| **drayton** | `address`, `command` | 0xHEX / int | 16-bit address, 8-bit command. |
| **dyson** | `address`, `command` | 0xHEX / int | 16-bit code, 8-bit index. |
| **gobox** | `data` | int | Single integer code. |
| **keeloq** | `encrypted`, `serial` | 0xHEX / int | 32-bit encrypted portion and 32-bit serial. |
| **magiquest** | `id`, `magnitude` | 0xHEX / int | 32-bit Wand ID and 16-bit magnitude. |
| **mirage** | `data` | array | Array of 0xHEX or integers (bytes). |
| **nexa** | `device` | 0xHEX / int | 32-bit device ID. |
| | `group`, `state`, `channel`, `level` | int | 8-bit fields. |
| **rc_switch** | `code` | 0xHEX / int64 | 64-bit code. |
| | `protocol` | int | Optional, default 1. |
| **roomba** | `command` | 0xHEX / int | 8-bit command. |
| **symphony** | `data` | 0xHEX / int | 32-bit code. |
| | `nbits` | int | Optional, default 12. |
| **toshiba_ac** | `rc_code_1`, `rc_code_2` | 0xHEX / int64 | Two 64-bit data chunks. |
| **toto** | `command` | 0xHEX / int | 8-bit command. |

**Data type legend:**
- **0xHEX / int** — A JSON string starting with `0x` (e.g. `"0xFF00"`) or a raw integer (e.g. `65280`).
- **0xHEX / int64** — Same, but supports 64-bit values (needed for `samsung`, `toshiba_ac`).
- **array** — A JSON array, e.g. `[255, 128, "0x0A"]`.
