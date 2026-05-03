# ir2mqtt_bridge Component

The `ir2mqtt_bridge` is an external ESPHome component that turns any ESP32 into an IR bridge. It handles IR reception and transmission, communicates with the IR2MQTT backend via MQTT or serial, and manages protocol selection and status feedback.

## Installation

Add the component to your ESPHome YAML via `external_components`:

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/steelcuts/ir2mqtt_bridge
      ref: main
    components: [ir2mqtt_bridge]
```

ESPHome fetches and compiles the component automatically — no manual download needed.

## Configuration Reference

```yaml
ir2mqtt_bridge:
  receivers: [rx1, rx2]         # List of remote_receiver IDs (optional)
  transmitters: [tx1, tx2]      # List of remote_transmitter IDs (optional)
  uart_id: bridge_uart          # UART component ID for serial mode (optional)
  device_id: "livingroom"       # Custom ID used in MQTT topics (default: MAC address)
  status_led: status_light      # Light component ID for visual feedback (optional)
  protocols:                    # Protocols active on first boot (default: all except rc_switch)
    - nec
    - samsung
    - raw
```

### `receivers`
List of `remote_receiver` component IDs. Each receiver consumes one RMT RX channel. Omit if the bridge is transmit-only.

### `transmitters`
List of `remote_transmitter` component IDs. Each transmitter consumes one RMT TX channel. Omit if the bridge is receive-only.

### `uart_id`
References an ESPHome `uart:` component. When set, the bridge reads JSON commands from RX and writes JSON output to TX — enabling **serial (USB) mode**. Requires `logger: baud_rate: 0` to prevent the ESPHome logger from interfering with UART0.

### `device_id`
Sets the base for all MQTT topics: `ir2mqtt/bridge/<device_id>/...`. Defaults to the device MAC address (e.g. `28562f9056c4`). Use a short, memorable name per location (e.g. `livingroom`, `bedroom`).

### `status_led`
References a `light:` component (WS2812B or compatible addressable LED) for visual feedback. See [Status LED](#status-led) below.

### `protocols`
The list of IR protocols active on first boot. Persisted to flash — changes made via the IR2MQTT UI are retained across reboots. Defaults to all supported protocols except `rc_switch`. See [Supported Protocols](#supported-protocols).

---

## Supported Protocols

`nec`, `samsung`, `samsung36`, `sony`, `panasonic`, `rc5`, `rc6`, `jvc`, `lg`, `coolix`, `pioneer`, `dish`, `midea`, `haier`, `raw`, `pronto`, `aeha`, `abbwelcome`, `beo4`, `byronsx`, `canalsat`, `canalsat_ld`, `dooya`, `drayton`, `dyson`, `gobox`, `keeloq`, `magiquest`, `mirage`, `nexa`, `rc_switch`, `roomba`, `symphony`, `toshiba_ac`, `toto`

### Carrier Frequencies

Most protocols use 38 kHz, but several deviate. A standard 38 kHz receiver will pick up nearby frequencies (36–40 kHz) with reduced sensitivity — learning may require holding the remote closer. For protocols far outside this range (Dish at 57.6 kHz), a matching receiver is needed.

| Protocol | Carrier | Notes |
|----------|---------|-------|
| `nec` | 38 kHz | Most common; safe baseline for testing |
| `samsung`, `samsung36` | 38 kHz | |
| `jvc` | 38 kHz | |
| `lg` | 38 kHz | |
| `coolix` | 38 kHz | |
| `midea` | 38 kHz | |
| `haier` | 38 kHz | |
| `aeha` | 38 kHz | Japanese home appliances |
| `toshiba_ac` | 38 kHz | |
| `rc5` | 36 kHz | Philips standard; 38 kHz receiver works at close range |
| `rc6` | 36 kHz | Used by many set-top boxes |
| `panasonic` | 36.7 kHz | 38 kHz receiver works at close range |
| `sony` (SIRC) | 40 kHz | 38 kHz receiver works at close range |
| `pioneer` | 40 kHz | |
| `dish` | 57.6 kHz | Requires a matching 56–58 kHz receiver |
| `raw` | varies | Frequency is captured and replayed as-is |
| `pronto` | encoded | Carrier frequency is stored in the Pronto hex string |
| `rc_switch` | RF (433 MHz) | **Not IR** — requires a 433 MHz RF receiver, not an IR module |

:::warning Not all protocols use 38 kHz
If a protocol consistently fails to learn on a standard 38 kHz module, the carrier frequency mismatch is the most likely cause — not a hardware fault. Start with `nec`, `samsung`, or `sony` to verify basic hardware function.
:::

---

## Status LED

Requires a `light:` component referenced via `status_led:`. A single WS2812B LED is sufficient.

```yaml
light:
  - platform: esp32_rmt_led_strip
    id: status_light
    internal: true
    rgb_order: GRB
    chipset: WS2812
    pin: GPIO13
    num_leds: 1
    name: "IR Bridge Status LED"
```

| Color | Event |
|-------|-------|
| Blue fade | Booting |
| Dim blue | Idle |
| Green flash | MQTT connected / first valid serial command |
| Red flash | MQTT disconnected |
| Orange flash | Invalid JSON / unknown command / send failed |
| Purple/magenta flash | IR signal received |
| Bright blue flash | IR signal transmitted |

---

## MQTT & Serial Protocol

The bridge communicates using newline-delimited JSON over MQTT or UART. For the full protocol reference — topics, message formats, send commands, and payload fields per protocol — see the [MQTT Topic Reference](/mqtt).

---

## How It Works Internally

The component uses **conditional compilation** to keep the firmware binary as small as possible. When ESPHome parses your YAML, the `__init__.py` checks which features are active and injects compiler flags accordingly:

| Flag | Active when |
|------|-------------|
| `USE_MQTT` | `mqtt:` block is present in the YAML |
| `USE_UART` | `uart_id:` is set |
| `USE_LIGHT` | `status_led:` is set |

If a feature is not used, its code is never compiled into the firmware — saving flash memory.

MQTT does not require an explicit ID in the config because ESPHome exposes it as a global singleton (`mqtt::global_mqtt_client`). The component detects it automatically.
