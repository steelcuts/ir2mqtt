# Troubleshooting

## Common Problems

| Problem | Fix |
|---------|-----|
| Device not appearing in Home Assistant | Enable MQTT Discovery in HA; verify broker credentials match. |
| IR codes not learning | Use a 38 kHz receiver; move closer to the sensor. |
| Bridge shows as offline | Check ESPHome logs (USB or WiFi); verify MQTT broker connectivity. |
| Serial bridge not detected | Check port permissions (`ls -l /dev/ttyUSB*`); ensure no other process holds the port. |
| Automations not triggering | Ensure the device is selected correctly in the trigger, and verify the physical remote code matches the learned code. |

## MQTT Connection Issues

:::warning MQTT credentials mismatch
IR2MQTT reads credentials from `/data/options.json` (managed by the HA Supervisor). If you changed your MQTT broker password, restart the IR2MQTT add-on — it does not auto-reload credentials.
:::

- **Wrong base topic:** All topics are prefixed with `ir2mqtt/`. If you changed the topic prefix in your MQTT broker ACL, make sure it matches.
- **Auth error in logs:** Look for `[MQTT] Connection refused` in the IR2MQTT logs. Double-check username and password in the add-on configuration.
- **Broker not reachable:** If running in standalone Docker mode, ensure the container is on the same Docker network as your broker, or use the host IP instead of `localhost`.

## IR Codes Not Working

- **Wrong protocol:** If a device doesn't respond to learned codes, try disabling all protocols except the one you expect (e.g. NEC for most TVs) on the Bridge settings page.
- **Echo suppression blocking codes:** If a button triggers correctly the first time but not immediately after, echo suppression may be too aggressive. Reduce the timeout or disable **Ignore Others** in the bridge settings.
- **RAW codes unreliable:** RAW captures are sensitive to timing. Use **Smart Learning** (multiple presses) to get a more consistent signal. If it still fails, try capturing from a shorter distance.
- **RC5 protocol:** RC5 is currently broken in ESPHome upstream. Use RAW as a workaround for RC5 devices.

## Home Assistant Integration

- **Entities not created after enabling discovery:** HA caches MQTT discovery payloads. Go to **Settings → Devices & Services → MQTT** and click **Re-configure** or restart HA.
- **Button entity missing:** Check that the button has **Output (Send)** capability enabled.
- **Binary sensor always OFF:** The button needs **Input (Receive)** capability enabled, and a signal must be received at least once to register the entity state.
- **Device trigger not available in automations:** The button needs **Event (Trigger)** capability enabled.

## Bridge / Hardware Issues

:::tip Loopback test
Use the **Diagnostics → Loopback Test** on the Bridges page to verify your hardware. It sends a test code and checks if the receiver picks it up — great for confirming TX/RX wiring.
:::

- **Bridge discovered but immediately goes offline:** Check power supply stability on the ESP32. Brownouts during IR transmission are common with weak USB power.
- **Serial bridge port disappears:** On Linux, add your user to the `dialout` group: `sudo usermod -aG dialout $USER`. Reconnect after re-login.
- **Multiple bridges causing cross-talk:** Enable **Allowed Bridges (Receiving)** on devices to restrict which bridge can trigger them, and enable **Ignore Others** in echo suppression.

## Docker / Standalone

- **Data not persisting after restart:** Ensure `/data` is mounted as a Docker volume: `-v ir2mqtt_data:/data`.
- **Web UI not reachable:** The default port is `8099`. Check that the port is exposed: `-p 8099:8099`.
- **`options.yaml` changes not applied:** Restart the container after editing the file — settings are only read on startup.
