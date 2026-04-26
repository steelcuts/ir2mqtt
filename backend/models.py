from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --- MODELS ---
class IRCode(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    protocol: str
    payload: dict[str, Any] = Field(default_factory=dict)
    raw_tolerance: int | None = 20


class IRButton(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    icon: str = "remote"
    code: IRCode | None = None
    is_output: bool = True
    is_input: bool = False
    is_event: bool = True
    input_mode: str = "momentary"
    input_off_delay_s: int = 1
    ordering: int = 0


class IRButtonCreate(BaseModel):
    name: str
    icon: str = "remote"
    code: IRCode | None = None
    is_output: bool = True
    is_input: bool = False
    is_event: bool = True
    input_mode: str = "momentary"
    input_off_delay_s: int = 1

    @field_validator("icon")
    @classmethod
    def clean_icon(cls, v: str) -> str:
        return v.replace("mdi:", "").replace("mdi-", "")


class IRDevice(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    icon: str = "remote-tv"
    buttons: list[IRButton] = []
    target_bridges: list[str] = []
    allowed_bridges: list[str] = []
    ordering: int = 0


class IRDeviceCreate(BaseModel):
    name: str
    icon: str = "remote-tv"
    target_bridges: list[str] = []
    allowed_bridges: list[str] = []
    buttons: list[IRButtonCreate] = []

    @field_validator("icon")
    @classmethod
    def clean_icon(cls, v: str) -> str:
        return v.replace("mdi:", "").replace("mdi-", "")


class IRDeviceUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    target_bridges: list[str] | None = None
    allowed_bridges: list[str] | None = None

    @field_validator("icon")
    @classmethod
    def clean_icon(cls, v: str | None) -> str | None:
        if v is not None:
            return v.replace("mdi:", "").replace("mdi-", "")
        return v


class IRButtonUpdate(IRButtonCreate):
    name: str | None = None
    icon: str | None = None

    @field_validator("icon")
    @classmethod
    def clean_icon(cls, v: str | None) -> str | None:
        if v is not None:
            return v.replace("mdi:", "").replace("mdi-", "")
        return v


class ReorderPayload(BaseModel):
    ids: list[str]


class IRAutomationAction(BaseModel):
    type: str  # "ir_send", "delay", "event"
    device_id: str | None = None
    button_id: str | None = None
    target: str | None = None
    delay_ms: int | None = None
    event_name: str | None = None


class SequenceItem(BaseModel):
    device_id: str | None = None
    button_id: str | None = None


class IRAutomationTrigger(BaseModel):
    type: str = "single"  # single, multi, sequence, device_inactivity

    # --- single / multi / sequence fields ---
    device_id: str | None = None
    button_id: str | None = None
    count: int = 1
    window_ms: int = 2000
    sequence: list[SequenceItem] = Field(default_factory=list)
    reset_on_other_input: bool = True

    # --- device_inactivity fields ---
    # How long (seconds) the device must be silent before the automation fires.
    timeout_s: float = 30.0
    # Which IR events count as "activity": "received", "sent", or "both".
    watch_mode: Literal["received", "sent", "both"] = "received"
    # Optional whitelist: only these button IDs count as activity (None = all).
    button_filter: list[str] | None = None
    # Optional blacklist: these button IDs never count as activity.
    button_exclude: list[str] | None = None
    # How the trigger re-arms after firing:
    #   "always"   – re-arms immediately on next activity (default)
    #   "cooldown" – waits cooldown_s seconds before accepting new activity
    #   "never"    – fires exactly once per session; manual re-enable required
    rearm_mode: Literal["always", "cooldown", "never"] = "always"
    # Cooldown duration in seconds (only relevant when rearm_mode == "cooldown").
    cooldown_s: float = 0.0

    @field_validator("timeout_s")
    @classmethod
    def timeout_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("timeout_s must be greater than 0")
        return v

    # If True (default), the timer only starts after the first qualifying activity
    # is observed. If False, the timer starts immediately when the automation loads.
    require_initial_activity: bool = True
    # If True (default), IR codes sent by this automation's own ir_send actions
    # do not reset the inactivity timer, preventing feedback loops.
    ignore_own_actions: bool = True


class IRAutomation(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str | None = None
    name: str
    enabled: bool = True
    allow_parallel: bool = False
    ordering: int = 0

    triggers: list[IRAutomationTrigger] = []

    # HA Integration
    ha_expose_button: bool = False

    actions: list[IRAutomationAction] = []


class HistoryItem(IRCode):
    timestamp: float | None = None
    channel: str | list[str] | None = None
    ignored: bool | None = None


class BridgeSettings(BaseModel):
    echo_enabled: bool = False
    echo_timeout: int = 500
    echo_smart: bool = True
    echo_ignore_self: bool = True
    echo_ignore_others: bool = False


class SerialBridgeConfig(BaseModel):
    port: str
    baudrate: int = 115200


class ReceiverConfig(BaseModel):
    id: str


class TransmitterConfig(BaseModel):
    id: str


class Bridge(BaseModel):
    id: str
    name: str
    status: str
    connection_type: str | None = "mqtt"
    network_type: str | None = None
    ip: str | None = None
    serial_port: str | None = None
    mac: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    receivers: list[ReceiverConfig] = Field(default_factory=list)
    transmitters: list[TransmitterConfig] = Field(default_factory=list)
    enabled_protocols: list[str] = []
    last_seen: int | None = None
    version: str | None = None
    last_received: list[HistoryItem] = []
    last_sent: list[HistoryItem] = []
    settings: BridgeSettings | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_bridge(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Ensure default receivers/transmitters if missing
            if "receivers" not in data or not data["receivers"]:
                data["receivers"] = [{"id": "ir_rx_main"}]
            if "transmitters" not in data or not data["transmitters"]:
                data["transmitters"] = [{"id": "ir_tx_main"}]
        return data


class StatusResponse(BaseModel):
    mqtt_connected: bool
    bridges: list[Bridge]


class StatusOk(BaseModel):
    status: str = "ok"


class DuplicateDeviceResponse(BaseModel):
    status: str
    device: IRDevice


class DuplicateButtonResponse(BaseModel):
    status: str
    button: IRButton


class TriggerButtonResponse(BaseModel):
    status: str
    targets: list[str]


class AssignCodeResponse(BaseModel):
    status: str = "saved"


class TriggerAutomationResponse(BaseModel):
    status: str = "ok"
    message: str


class LoopbackTestResponse(BaseModel):
    status: str
    tx: str
    rx: str


class StopLoopbackTestResponse(BaseModel):
    status: str = "stopping"


class IrDbStatusResponse(BaseModel):
    exists: bool
    total_remotes: int
    total_codes: int
    last_updated: int | None


class SendIrDbCodeResponse(BaseModel):
    status: str = "sent"
    targets: list[str]


class StartLearningResponse(BaseModel):
    status: str = "listening"
    bridges: list[str]
    mode: str


class CancelLearningResponse(BaseModel):
    status: str = "cancelled"


class AppModeResponse(BaseModel):
    status: str = "ok"
    mode: str
    topic_style: Literal["name", "id"]
    locked: bool
    log_level: str
    echo_suppression_ms: int | None
    version: str | None = None


class LogLevelResponse(BaseModel):
    status: str = "ok"
    log_level: str


class MqttSettings(BaseModel):
    broker: str | None = None
    port: int = 1883
    user: str | None = None
    password: str | None = None


class MqttTestResponse(BaseModel):
    status: str
    message: str


class ImportConfigResponse(BaseModel):
    status: str = "ok"
    detail: str


class IrDbBrowseResponse(BaseModel):
    name: str
    type: str
    path: str


class IrDbSearchResponse(BaseModel):
    path: str
    name: str
