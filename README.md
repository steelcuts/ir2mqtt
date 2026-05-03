# IR2MQTT

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-HA--App-blue)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)
[![Hackaday](https://img.shields.io/badge/Hackaday-Featured-05979f)](https://hackaday.com/2026/05/02/ir-device-control-that-lives-off-the-cloud)

**The Ultimate IR Gateway for Smart Homes & MQTT.**

![IR2MQTT Demo](.github/assets/showcase.gif)

IR2MQTT bridges the gap between physical Infrared devices and your smart home. It replaces tedious YAML configuration with a modern, reactive Web UI to manage devices, learn IR codes, and create powerful automations — entirely local, no cloud, no account, no subscriptions.

---

## Documentation

Full documentation — hardware setup, wiring, ESPHome bridge component, MQTT reference, automations, and more — is available at:

**[steelcuts.github.io/ir2mqtt](https://steelcuts.github.io/ir2mqtt/)**

---

## Quick Start

### Option 1: Home Assistant Add-on

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fsteelcuts%2Fir2mqtt-ha-app)

1. Click the button above to add the repository, or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/steelcuts/ir2mqtt-ha-app`.
2. Find **IR2MQTT** in the store and click **Install**.
3. Enter your MQTT broker details in the **Configuration** tab.
4. Click **Start** and open the Web UI.

### Option 2: Docker

```yaml
services:
  ir2mqtt:
    image: ghcr.io/steelcuts/ir2mqtt:latest
    container_name: ir2mqtt
    restart: unless-stopped
    ports:
      - "8099:8099"
    environment:
      - MQTT_BROKER=192.168.1.100
      - MQTT_USER=mqtt_user
      - MQTT_PASS=mqtt_password
      - APP_MODE=standalone   # or 'home_assistant'
    volumes:
      - ./data:/data
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0  # optional: serial bridge
```

```bash
docker-compose up -d
# Web UI: http://<your-ip>:8099
```

---

## License

MIT — see [LICENSE](LICENSE.md) for details.

## Credits

- **Flipper-IRDB** & **Probono IRDB** — IR code databases
- **Material Design Icons** — UI icons
- **Vue.js**, **Vite**, **Tailwind CSS** — frontend stack
- **FastAPI**, **SQLAlchemy**, **paho-mqtt** — backend stack
- **ESPHome** — bridge firmware framework
