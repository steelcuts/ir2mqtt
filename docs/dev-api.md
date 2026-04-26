# REST API

All routes are prefixed with `/api`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | MQTT connection status + bridge list |
| GET/POST | `/api/devices` | List / create devices |
| PUT | `/api/devices/order` | Reorder devices |
| PUT/DELETE | `/api/devices/{id}` | Update / delete a device |
| POST | `/api/devices/{id}/duplicate` | Duplicate a device |
| POST/PUT/DELETE | `/api/devices/{id}/buttons/{btn_id}` | Create / update / delete a button |
| POST | `/api/devices/{id}/buttons/{btn_id}/trigger` | Send IR code for a button |
| POST | `/api/devices/{id}/buttons/{btn_id}/assign_code` | Assign last learned code |
| GET | `/api/bridges` | List bridges |
| DELETE | `/api/bridges/{id}` | Remove a bridge |
| PUT | `/api/bridges/{id}/settings` | Update bridge settings |
| POST | `/api/bridges/{id}/protocols` | Set enabled protocols |
| GET | `/api/bridges/serial/ports` | List available serial ports |
| POST | `/api/bridges/serial` | Add a serial bridge |
| DELETE | `/api/bridges/serial/{id}` | Remove a serial bridge |
| POST | `/api/learn` | Start IR learning (`?bridges=…&smart=true`) |
| POST | `/api/learn/cancel` | Cancel learning |
| GET | `/api/irdb/status` | IR database status |
| POST | `/api/irdb/sync` | Download/update IR databases |
| GET | `/api/irdb/browse` | Browse IR database (`?path=…`) |
| GET | `/api/irdb/search` | Search IR database (`?q=…`) |
| GET | `/api/irdb/file` | Load IR file (`?path=…`) |
| POST | `/api/irdb/send_code` | Send a raw IR code (test) |
| GET/POST/PUT/DELETE | `/api/automations{/id}` | CRUD for automations |
| POST | `/api/automations/{id}/trigger` | Manually trigger an automation |
| GET/PUT | `/api/settings/app` | App mode + topic style |
| GET/PUT | `/api/settings/mqtt` | MQTT broker settings |
| POST | `/api/settings/mqtt/test` | Test MQTT connection |
| PUT | `/api/settings/log_level` | Set log level |
| GET/POST | `/api/config/export`, `/api/config/import` | Backup / restore config |
| POST | `/api/reset` | Factory reset |
| POST/DELETE | `/api/test/loopback` | Start / stop loopback hardware test |