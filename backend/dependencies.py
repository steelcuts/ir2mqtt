from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

from .database import DatabaseManager, get_db

if TYPE_CHECKING:
    from logging import Logger

    from .automations import AutomationManager
    from .bridge_manager import BridgeManager
    from .config import Settings
    from .ir_db import IrDbManager
    from .mqtt import MQTTManager
    from .state import StateManager


def get_state_manager(request: Request) -> "StateManager":
    return request.app.state.state_manager


def get_mqtt_manager(request: Request) -> "MQTTManager":
    return request.app.state.mqtt_manager


def get_bridge_manager(request: Request) -> "BridgeManager":
    return request.app.state.mqtt_manager.bridge_manager


def get_automation_manager(request: Request) -> "AutomationManager":
    return request.app.state.automation_manager


def get_irdb_manager(request: Request) -> "IrDbManager":
    return request.app.state.irdb_manager


def get_settings(request: Request) -> "Settings":
    return request.app.state.settings


def get_logger(request: Request) -> "Logger":
    return request.app.state.logger


# --- Annotated Dependencies (Improved DI) ---
DatabaseDep = Annotated[DatabaseManager, Depends(get_db)]
StateManagerDep = Annotated["StateManager", Depends(get_state_manager)]
MQTTManagerDep = Annotated["MQTTManager", Depends(get_mqtt_manager)]
BridgeManagerDep = Annotated["BridgeManager", Depends(get_bridge_manager)]
AutomationManagerDep = Annotated["AutomationManager", Depends(get_automation_manager)]
IrDbManagerDep = Annotated["IrDbManager", Depends(get_irdb_manager)]
SettingsDep = Annotated["Settings", Depends(get_settings)]
LoggerDep = Annotated["Logger", Depends(get_logger)]
