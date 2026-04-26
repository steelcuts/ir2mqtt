import random

from pydantic import BaseModel, Field


class ProtocolDef(BaseModel):
    fields: list[str]
    hex_fields: list[str] = Field(default_factory=list)
    defaults: dict[str, str] = Field(default_factory=dict)
    is_json: bool = False


PROTOCOL_CONFIG = {
    "nec": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "panasonic": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "rc5": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "rc6": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "samsung36": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "dish": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "sharp": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "sanyo": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "rca": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "samsung": ProtocolDef(fields=["data", "nbits"], hex_fields=["data"], defaults={"nbits": "32"}),
    "sony": ProtocolDef(fields=["data", "nbits"], hex_fields=["data"], defaults={"nbits": "32"}),
    "lg": ProtocolDef(fields=["data", "nbits"], hex_fields=["data"], defaults={"nbits": "32"}),
    "toshiba": ProtocolDef(fields=["data", "nbits"], hex_fields=["data"], defaults={"nbits": "32"}),
    "whynter": ProtocolDef(fields=["data", "nbits"], hex_fields=["data"], defaults={"nbits": "32"}),
    "jvc": ProtocolDef(fields=["data"], hex_fields=["data"]),
    "midea": ProtocolDef(fields=["data"], hex_fields=["data"]),
    "haier": ProtocolDef(fields=["data"], hex_fields=["data"]),
    "pioneer": ProtocolDef(fields=["rc_code_1", "rc_code_2"], hex_fields=["rc_code_1", "rc_code_2"]),
    "coolix": ProtocolDef(fields=["first", "second"], hex_fields=["first", "second"]),
    "raw": ProtocolDef(fields=["data"], is_json=True),
    "pronto": ProtocolDef(fields=["data"]),
    "aeha": ProtocolDef(fields=["address", "data"], hex_fields=["address"], is_json=True),
    "abbwelcome": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "beo4": ProtocolDef(fields=["command", "source"], hex_fields=["command", "source"]),
    "byronsx": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "canalsat": ProtocolDef(fields=["device", "command"], hex_fields=["device", "command"]),
    "canalsat_ld": ProtocolDef(fields=["device", "command"], hex_fields=["device", "command"]),
    "dooya": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "drayton": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "dyson": ProtocolDef(fields=["address", "command"], hex_fields=["address", "command"]),
    "gobox": ProtocolDef(fields=["data"], is_json=True),
    "keeloq": ProtocolDef(fields=["encrypted", "serial"], hex_fields=["encrypted", "serial"]),
    "magiquest": ProtocolDef(fields=["id", "magnitude"], hex_fields=["id"]),
    "mirage": ProtocolDef(fields=["data"], is_json=True),
    "nexa": ProtocolDef(fields=["device", "group", "state", "channel", "level"], hex_fields=["device", "group", "state", "channel", "level"]),
    "rc_switch": ProtocolDef(fields=["code", "protocol"], hex_fields=["code"]),
    "roomba": ProtocolDef(fields=["command"], hex_fields=["command"]),
    "symphony": ProtocolDef(fields=["data", "nbits"], hex_fields=["data"], defaults={"nbits": "12"}),
    "toshiba_ac": ProtocolDef(fields=["rc_code_1", "rc_code_2"], hex_fields=["rc_code_1", "rc_code_2"]),
    "toto": ProtocolDef(fields=["command"], hex_fields=["command"]),
}

ALL_PROTOCOLS = sorted(PROTOCOL_CONFIG.keys())


def generate_random_hex(bytes_count: int) -> str:
    return "0x" + "".join([random.choice("0123456789ABCDEF") for _ in range(bytes_count * 2)])


def sanitize_topic(name: str) -> str:
    return name.lower().replace(" ", "_").replace("+", "plus").replace("#", "sharp").replace("/", "_").replace("", "_")


class Topics:
    """Centralized definition of MQTT topics."""

    BASE = "ir2mqtt"

    @staticmethod
    def bridge_root(bid: str) -> str:
        return f"{Topics.BASE}/bridge/{bid}"

    @staticmethod
    def bridge_config(bid: str) -> str:
        return f"{Topics.bridge_root(bid)}/config"

    @staticmethod
    def bridge_state(bid: str) -> str:
        return f"{Topics.bridge_root(bid)}/state"

    @staticmethod
    def bridge_command(bid: str) -> str:
        return f"{Topics.bridge_root(bid)}/command"

    @staticmethod
    def bridge_response(bid: str) -> str:
        return f"{Topics.bridge_root(bid)}/response"

    @staticmethod
    def bridge_received(bid: str) -> str:
        return f"{Topics.bridge_root(bid)}/received"

    @staticmethod
    def bridge_availability(bid: str) -> str:
        return f"{Topics.bridge_root(bid)}/availability"

    @staticmethod
    def cmd_ha(dev_id: str, btn_id: str) -> str:
        return f"{Topics.BASE}/cmd/{dev_id}/{btn_id}"

    @staticmethod
    def cmd_sa(dev_name: str, btn_name: str) -> str:
        return f"{Topics.BASE}/devices/{sanitize_topic(dev_name)}/{sanitize_topic(btn_name)}/in"

    @staticmethod
    def automation_trigger_id(auto_id: str) -> str:
        return f"{Topics.BASE}/automation/{auto_id}/trigger"

    @staticmethod
    def automation_trigger_name(auto_name: str) -> str:
        return f"{Topics.BASE}/automations/{sanitize_topic(auto_name)}/trigger"
