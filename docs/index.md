---
layout: home
hero:
  name: "IR2MQTT"
  text: "The Ultimate IR Gateway"
  tagline: "Bridge the gap between physical Infrared devices and your smart home."
  actions:
    - theme: brand
      text: Get Started
      link: /hardware-setup
    - theme: alt
      text: View on GitHub
      link: https://github.com/steelcuts/ir2mqtt
features:
  - title: Modern Web UI
    details: Replaces tedious YAML configuration with a reactive Web UI to manage devices, learn IR codes, and create powerful automations.
  - title: MQTT Auto-Discovery
    details: Integrates seamlessly into Home Assistant using MQTT Discovery, creating devices, buttons, and sensors automatically.
  - title: Integrated IR Database
    details: Built-in support for thousands of IR codes from the Flipper Zero and Probono databases. Import them with a single click.
---

## Getting Started

Follow these four steps to get IR2MQTT up and running:

**1. Flash a Bridge**

Flash an ESP32 with the IR2MQTT ESPHome firmware. Connect an IR receiver (38 kHz) and an IR LED to GPIO pins. New to this? The **[Hardware Setup Guide](/hardware-setup)** covers everything: ESP32 board selection, IR components, wiring, ESPHome installation, and step-by-step configuration.

**2. Set Up an MQTT Broker**

IR2MQTT and your ESP32 bridges communicate via MQTT — you need a broker running somewhere on your network. The quickest option is the **Mosquitto add-on** in Home Assistant (one click in the add-on store). For standalone setups, a Docker container works just as well. Once the broker is running, enter the credentials in the IR2MQTT add-on options or `/data/options.yaml`. See the [MQTT Broker Setup](/hardware-setup#setting-up-the-mqtt-broker) section for step-by-step instructions.

**3. Add a Device**

Open the Web UI and create a device — either from a built-in template, the IR Database, or manually. Use **Learning Mode** to capture codes from your physical remote.

**4. Integrate with Home Assistant**

Set the App Mode to **Home Assistant**. IR2MQTT will publish MQTT Discovery payloads automatically, creating `button`, `binary_sensor`, and device trigger entities in HA without any manual configuration.
