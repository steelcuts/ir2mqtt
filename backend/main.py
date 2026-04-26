import asyncio
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket
from fastapi.staticfiles import StaticFiles

from .automations import AutomationManager
from .config import get_settings, set_main_loop, setup_logging
from .database import DatabaseManager
from .db.session import get_session_maker, init_db
from .integrations import get_integration
from .ir_db import IrDbManager
from .models import StatusResponse
from .mqtt import MQTTManager

# Import Routers
from .routers import (
    automations,
    bridges,
    devices,
    diagnostics,
    irdb,
    serial_bridges,
)
from .routers import (
    settings as settings_router,
)
from .serial_manager import SerialTransport
from .state import StateManager
from .utils import update_options_file
from .websockets import log_broadcaster, ws_clients


# --- FASTAPI LIFESPAN & APP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger = setup_logging(settings.log_level)

    logger.info("Application starting up...")
    loop = asyncio.get_running_loop()
    set_main_loop(loop)

    app.state.logger = logger
    app.state.settings = settings
    state_manager = StateManager()
    app.state.state_manager = state_manager

    # Initialize Managers
    db_manager = DatabaseManager(get_session_maker()())
    mqtt_manager = MQTTManager(state_manager, None)  # automation_manager set later
    automation_manager = AutomationManager(db_manager)
    irdb_manager = IrDbManager()
    mqtt_manager.automation_manager = automation_manager
    automation_manager.set_mqtt_manager(mqtt_manager)
    automation_manager.set_state_manager(state_manager)

    app.state.mqtt_manager = mqtt_manager
    app.state.automation_manager = automation_manager
    app.state.irdb_manager = irdb_manager

    automation_manager.set_logger(logger)

    logger.info("Initializing database...")
    await init_db()
    automation_manager.start()

    logger.info("Loading data from database...")
    async with db_manager as db:
        state_manager.devices = await db.load_all_devices()

    await automation_manager.load()
    logger.info("Data and automations loaded.")

    # Initialize Integration
    logger.info("Initializing integration: %s", settings.app_mode)
    current_integration = get_integration(settings.app_mode, state_manager, settings)
    mqtt_manager.set_integration(current_integration)

    logger.info("Setting up MQTT manager...")
    mqtt_manager.setup(loop, settings, logger)
    mqtt_manager.bridge_manager.set_on_message_cb(lambda bridge_id, msg_type, payload: mqtt_manager._handle_ir_received(bridge_id, payload))

    if settings.ignored_bridges:
        logger.info("Loading %d ignored bridge(s) from settings.", len(settings.ignored_bridges))
        mqtt_manager.bridge_manager.set_ignored_bridges(settings.ignored_bridges)
        # Derive which serial ports to suppress from the stored bridge_id in serial_bridges config
        mqtt_manager.bridge_manager.ignored_serial_ports = {cfg.port for b_id, cfg in settings.serial_bridges.items() if b_id in mqtt_manager.bridge_manager.ignored_bridge_ids}

    logger.info("Setting up serial bridges...")
    app.state.serial_transports = []

    def make_identified_cb(port, initial_bridge_id):
        def on_identified(new_bridge_id: str):
            current_key = None
            for k, c in list(settings.serial_bridges.items()):
                if c.port == port:
                    current_key = k
                    break
            if current_key and current_key != new_bridge_id:
                logger.warning("Serial bridge on %s changed ID: %s → %s", port, current_key, new_bridge_id)
                cfg = settings.serial_bridges.pop(current_key)
                settings.serial_bridges[new_bridge_id] = cfg
                update_options_file(
                    settings.options_file,
                    {"serial_bridges": {k: v.model_dump() for k, v in settings.serial_bridges.items()}},
                )

        return on_identified

    for b_id, sb_config in list(settings.serial_bridges.items()):
        st = SerialTransport(
            port=sb_config.port,
            baudrate=sb_config.baudrate,
            bridge_manager=mqtt_manager.bridge_manager,
            loop=loop,
            on_identified=make_identified_cb(sb_config.port, b_id),
        )
        app.state.serial_transports.append(st)
        st.start()

    logger.info("Starting log broadcaster.")
    log_task = asyncio.create_task(log_broadcaster())

    yield

    logger.info("Application shutting down...")
    log_task.cancel()
    automation_manager.stop()
    if mqtt_manager.client:
        mqtt_manager.client.loop_stop()
        logger.info("MQTT client loop stopped.")

    for st in app.state.serial_transports:
        await st.stop()
    logger.info("Serial transports stopped.")

    logger.info("Application shutdown complete.")


app = FastAPI(lifespan=lifespan)

# Include Routers
app.include_router(devices.router)
app.include_router(bridges.router)
app.include_router(serial_bridges.router)
app.include_router(automations.router)
app.include_router(settings_router.router)
app.include_router(irdb.router)
app.include_router(diagnostics.router)


# --- API ENDPOINTS ---
@app.websocket("/ws/events")
async def websocket_handler(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    app.state.logger.info("New websocket client connected.")
    try:
        # Send initial state on connect
        await websocket.send_json({"type": "mqtt_status", "connected": app.state.mqtt_manager.connected})
        app.state.logger.debug("Sent initial MQTT status to new websocket client.")
        await websocket.send_json(
            {
                "type": "bridges_updated",
                "bridges": app.state.mqtt_manager._get_bridges_list_for_broadcast(),
            }
        )
        app.state.logger.debug("Sent initial bridge list to new websocket client.")

        # Sync running automations
        for auto_id, count in list(app.state.automation_manager.running_automations.items()):
            await websocket.send_json(
                {
                    "type": "automation_progress",
                    "id": auto_id,
                    "status": "running",
                    "current_action_index": -1,
                    "running_count": count,
                }
            )
        if app.state.automation_manager.running_automations:
            app.state.logger.debug("Sent initial automation status to new websocket client.")

        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        ws_clients.discard(websocket)
        app.state.logger.info("Websocket client disconnected.")


@app.get("/api/status", response_model=StatusResponse)
async def get_status(request: Request = None):
    mqtt_manager = app.state.mqtt_manager if not request else request.app.state.mqtt_manager
    bridges = mqtt_manager._get_bridges_list_for_broadcast()
    return StatusResponse(mqtt_connected=mqtt_manager.connected, bridges=bridges)


# In a development environment (using docker-compose), the frontend is served by Vite.
# In production (like a Home Assistant app), the backend serves the built frontend.
if os.getenv("APP_ENV") != "development" and "pytest" not in sys.modules:
    app.mount("/", StaticFiles(directory="dist", html=True), name="static")
