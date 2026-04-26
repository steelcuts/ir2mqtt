# WebSocket API

IR2MQTT exposes a real-time WebSocket endpoint at `/ws/events`. The frontend uses it to reflect live state changes without polling. You can also connect to it to build custom integrations.

All messages are JSON objects with a `type` field plus event-specific data.

## Connecting

```js
const ws = new WebSocket('ws://ir2mqtt.local:8099/ws/events')

ws.onopen = () => console.log('connected')
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data)
  console.log(msg.type, msg)
}
ws.onclose = () => console.log('disconnected')
```

```bash
# Quick test with websocat
websocat ws://ir2mqtt.local:8099/ws/events
```

## Event Reference

### State Changes

**`mqtt_status`** — MQTT broker connection changed.
```json
{ "type": "mqtt_status", "connected": true }
```

**`bridges_updated`** — A bridge connected, disconnected, or updated its state. Contains the full bridges list.
```json
{ "type": "bridges_updated", "bridges": [ { "id": "mqtt_esp_living", "online": true, "name": "Living Room" } ] }
```

**`devices_updated`** / **`automations_updated`** — Configuration changed. Fetch fresh data from the REST API.
```json
{ "type": "devices_updated" }
```

### Live Activity

**`known_code_received`** — A learned IR code was received by a bridge.
```json
{ "type": "known_code_received", "button_id": "abc123", "ignored": false }
```

**`known_code_sent`** — A code was transmitted.
```json
{ "type": "known_code_sent", "button_id": "abc123" }
```

**`automation_progress`** — An automation is executing. Useful for visualizing step-by-step progress.
```json
{ "type": "automation_progress", "automation_id": "xyz", "step": 2, "total": 4 }
```

**`trigger_progress`** — A multi-press or sequence trigger is accumulating input.
```json
{ "type": "trigger_progress", "trigger_id": "xyz", "current": 2, "required": 3 }
```

**`inactivity_state`** — A Device Inactivity trigger changed state. Sent whenever the timer arms, fires, enters cooldown, or goes idle. The frontend uses this to render the live countdown bar.

```json
{
  "type": "inactivity_state",
  "automation_id": "abc",
  "trigger_index": 0,
  "state": "armed",
  "deadline": 1714123456.789
}
```

| Field | Description |
|-------|-------------|
| `automation_id` | ID of the automation this trigger belongs to. |
| `trigger_index` | Zero-based index of the trigger within the automation. |
| `state` | One of `armed` (timer running), `fired` (action executed), `cooldown` (waiting to rearm), `idle` (disarmed / cooldown ended). |
| `deadline` | Unix timestamp (seconds, float) of when the current timer expires. `null` when `state` is `idle`. |

**`log`** — Backend log line streamed in real-time.
```json
{ "type": "log", "message": "[MQTT] Bridge esp_living connected" }
```

## Notes

- The server sends a full state snapshot on connect so clients don't need to poll after connecting.
- The connection is unauthenticated — only expose the port on trusted networks.
- Reconnect with exponential backoff; the server closes idle connections after inactivity.
