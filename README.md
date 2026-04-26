# IR2MQTT

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-blue)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)

**The Ultimate IR Gateway for Smart Homes & MQTT.**

![IR2MQTT Demo](.github/assets/showcase.gif)

IR2MQTT bridges the gap between physical Infrared devices and your smart home. It replaces tedious YAML configuration with a modern, reactive Web UI to manage devices, learn IR codes, and create powerful automations.

---

## Documentation & Manual

For full details on features, configuration, MQTT topics, and development instructions, please visit the **IR2MQTT Documentation Site** or read the Markdown files in the `docs/` folder.

For details on ESPHome bridge setup please see the **[ir2mqtt_bridge Repository](https://github.com/steelcuts/ir2mqtt_bridge)**.



---

## Quick Start

### Option 1: Home Assistant Add-on

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fsteelcuts%2Fir2mqtt-addon)

1. Click the button above to add the repository, or manually go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/steelcuts/ir2mqtt-addon`.
2. Find **IR2MQTT** in the store and click **Install**.
3. In the **Configuration** tab, enter your MQTT broker details.
4. Click **Start** and open the Web UI.

### Option 2: Docker (Standalone)

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
      - /dev/ttyUSB0:/dev/ttyUSB0 # Adjust to your serial device
```

```bash
docker-compose up -d
# Web UI: http://<your-ip>:8099
```

---

## Resources

- [ESPHome Documentation](https://esphome.io)
- [Home Assistant MQTT Integration](https://www.home-assistant.io/integrations/mqtt/)
- [Flipper-IRDB](https://github.com/logickworkshop/Flipper-IRDB)
- [Probono IRDB](https://github.com/probonopd/irdb)
- [Mosquitto MQTT Broker](https://mosquitto.org)

## License

MIT — see [LICENSE](LICENSE) for details.

## Credits

- **Flipper-IRDB** & **Probono IRDB** — IR code databases
- **Material Design Icons** — UI icons
- **Vue.js**, **Vite**, **Tailwind CSS** — frontend stack
- **FastAPI**, **SQLAlchemy**, **paho-mqtt** — backend stack
- **ESPHome** — bridge firmware framework
