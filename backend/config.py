import asyncio
import json
import logging
import os
import sys
from functools import lru_cache
from typing import Any, Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from .models import BridgeSettings, SerialBridgeConfig

logger = logging.getLogger(__name__)


class YamlOptionsSource(PydanticBaseSettingsSource):
    def get_field_value(self, field: Any, field_name: str) -> Any:
        return None

    def __call__(self) -> dict[str, Any]:
        options = {}
        if "SUPERVISOR_TOKEN" in os.environ:
            options["app_mode"] = "home_assistant"

        ha_options_file = "/data/options.json"
        if os.path.exists(ha_options_file):
            try:
                with open(ha_options_file, encoding="utf-8") as f:
                    options.update(json.load(f) or {})
            except Exception as e:
                logger.error("Failed to load HA options from %s: %s", ha_options_file, e, exc_info=True)

        options_file = os.environ.get("OPTIONS_FILE", "/data/options.yaml")
        if os.path.exists(options_file):
            try:
                with open(options_file, encoding="utf-8") as f:
                    options.update(yaml.safe_load(f) or {})
            except Exception as e:
                logger.error("Failed to load options from %s: %s", options_file, e, exc_info=True)
        return options


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_mode: Literal["home_assistant", "standalone"] = "home_assistant"
    topic_style: Literal["name", "id"] = "name"
    echo_suppression_ms: int = 500
    bridge_settings: dict[str, BridgeSettings] = Field(default_factory=dict)
    serial_bridges: dict[str, SerialBridgeConfig] = Field(default_factory=dict)
    ignored_bridges: list[str] = Field(default_factory=list)
    log_level: str = "INFO"

    mqtt_broker: str | None = None
    mqtt_port: int = 1883
    mqtt_user: str | None = None
    mqtt_pass: str | None = None

    database_url: str = "sqlite+aiosqlite:////data/ir2mqtt.db"
    irdb_path: str = "/data/ir_db"
    options_file: str = "/data/options.yaml"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            YamlOptionsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


# --- LOGGING ---
log_queue = asyncio.Queue()
main_loop: asyncio.AbstractEventLoop | None = None


class QueueHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        if main_loop and not main_loop.is_closed():
            try:
                main_loop.call_soon_threadsafe(log_queue.put_nowait, log_entry)
            except Exception as e:
                print(f"Failed to queue log message: {e}", file=sys.stderr)


def setup_logging(log_level_str: str = "INFO"):
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    # Console Handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(log_level)
    root_logger.addHandler(ch)

    # Websocket Queue Handler
    qh = QueueHandler()
    qh.setFormatter(formatter)
    qh.setLevel(log_level)
    root_logger.addHandler(qh)

    # Force Uvicorn loggers to use our root logger and formatting
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

        # Prevent infinite logging loops with websockets at DEBUG level
        if log_level < logging.INFO:
            uvicorn_logger.setLevel(logging.INFO)

    return logging.getLogger("ir2mqtt")


def get_log_level_name() -> str:
    return logging.getLevelName(logging.getLogger().level)


def set_main_loop(loop: asyncio.AbstractEventLoop):
    global main_loop
    main_loop = loop


def set_log_level(level_str: str):
    log_level = getattr(logging, level_str.upper(), None)
    if log_level is not None:
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        for handler in root_logger.handlers:
            handler.setLevel(log_level)

        # Update Uvicorn loggers as well
        for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            uv_logger = logging.getLogger(logger_name)
            if log_level < logging.INFO:
                uv_logger.setLevel(logging.INFO)
            else:
                uv_logger.setLevel(log_level)

        logging.getLogger("ir2mqtt").info("Log level set to %s", level_str.upper())
