# Settings

## UI Settings
- **Language & Theme:** Choose your preferred display language and color scheme (Dark, Gray, Light).
- **View Mode:** The Devices page can be toggled between Compact, Normal, and Large layouts using the view icons in the top bar.
- **Indications:** Enable visual feedback (flashing) when codes are received or automations run. You can also optionally flash codes that were blocked by echo suppression.

## App Mode
- **Home Assistant:** Automatically discovers entities in HA using the MQTT Discovery protocol.
- **Standalone:** Uses generic MQTT topics (`ir2mqtt/devices/...`) for integration with other systems like Node-RED or OpenHAB.

## Configuration
- **Transfer:** Granular export/import of devices and automations. You can select specific items to backup or restore.
- **Factory Reset:** Wipes all data and restores the system to a clean state.

## Advanced Configuration (`options.yaml`)

While the Web UI is the recommended way to manage your setup, you can manually edit the `/data/options.yaml` file if necessary (e.g., when running as a standalone Docker container or for advanced configurations).

:::warning Home Assistant users
The `/data/options.json` file is managed by the HA Supervisor and is read-only. IR2MQTT reads it for MQTT credentials, but all internal app settings are stored in `/data/options.yaml`. Edit only `options.yaml`.
:::

Here is an example showing how to manually configure **Serial Bridges** and **Ignored Bridges**:

```yaml
# General App Settings
app_mode: "home_assistant"
topic_style: "name"
log_level: "INFO"

# Serial Bridges Configuration
# You can manually add USB/Serial bridges here.
# The key (e.g., 'serial_esp_livingroom') is the internal Bridge ID.
serial_bridges:
  serial_esp_livingroom:
    port: "/dev/ttyUSB0"
    baudrate: 115200

# Ignored Bridges
# A list of Bridge IDs that should be completely ignored by the app and hidden from the UI.
ignored_bridges:
  - "mqtt_bridge_old_livingroom"
  - "serial:/dev/ttyUSB1"
```

:::tip Applying changes
Restart IR2MQTT after editing `options.yaml` — settings are only loaded on startup.
:::
