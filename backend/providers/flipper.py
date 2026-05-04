import logging
import os
from pathlib import Path

from ..ir_base import (
    SUPPORTED_PROTOCOLS,
    IrRepoProvider,
    flipper_hex_to_int,
    parse_flipper_hex,
    standardize_ir_key,
)

logger = logging.getLogger(__name__)


class FlipperProvider(IrRepoProvider):
    def __init__(self):
        super().__init__(
            id="flipper",
            name="Flipper IRDB",
            url="https://github.com/logickworkshop/Flipper-IRDB/archive/refs/heads/main.zip",
        )
        self._total_buttons_seen = 0
        self._skip_counts: dict[str, int] = {
            "unsupported_protocol": 0,
            "malformed_raw": 0,
            "missing_name": 0,
        }

    def convert(self, raw_root: Path) -> list[dict]:
        remotes = []
        self._total_buttons_seen = 0
        self._skip_counts = {k: 0 for k in self._skip_counts}

        for root, dirs, files in os.walk(raw_root):
            dirs[:] = [d for d in dirs if d.lower() not in ["assets", "_converted_", ".git"]]

            for file in files:
                if not file.endswith(".ir"):
                    continue

                source_file = Path(root) / file
                rel_path = source_file.relative_to(raw_root)

                buttons = self._parse_ir_file(source_file)
                if buttons:
                    path = f"{self.id}/{rel_path.with_suffix('')}"
                    remotes.append(
                        {
                            "path": path,
                            "name": source_file.stem,
                            "provider": self.id,
                            "source_file": file,
                            "buttons": buttons,
                        }
                    )

        total_imported = sum(len(r["buttons"]) for r in remotes)
        total_skipped = sum(self._skip_counts.values())
        self.last_convert_stats = {
            "total_rows": self._total_buttons_seen,
            "imported": total_imported,
            "skipped": total_skipped,
            "skip_reasons": dict(self._skip_counts),
        }
        logger.info(
            "[%s] Conversion stats: %d buttons seen, %d imported, %d skipped (protocol=%d, malformed_raw=%d, missing_name=%d)",
            self.name,
            self._total_buttons_seen,
            total_imported,
            total_skipped,
            self._skip_counts["unsupported_protocol"],
            self._skip_counts["malformed_raw"],
            self._skip_counts["missing_name"],
        )
        return remotes

    def _parse_ir_file(self, path: Path) -> list[dict]:
        buttons = []
        current_btn = {}
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" in line:
                        key, val = line.split(":", 1)
                        key = key.strip().lower()
                        val = val.strip()
                        if key == "name":
                            if current_btn:
                                self._finalize_button(current_btn, buttons)
                            current_btn = {"name": val}
                        elif current_btn is not None:
                            current_btn[key] = val
                if current_btn:
                    self._finalize_button(current_btn, buttons)
        except Exception as e:
            logger.debug("Failed to parse Flipper IR file %s: %s", path, e, exc_info=True)
        return buttons

    def _finalize_button(self, btn_data: dict, buttons_list: list):
        self._total_buttons_seen += 1
        if "name" not in btn_data:
            self._skip_counts["missing_name"] += 1
            return

        std = standardize_ir_key(btn_data["name"])
        name = std["name"]
        icon = std["icon"]
        protocol = btn_data.get("protocol", "").lower()
        nbits = None

        if protocol in ["necext", "nec42"]:
            protocol = "nec"
        elif protocol == "samsung32":
            protocol = "samsung"
            nbits = 32
        elif protocol == "sirc":
            protocol = "sony"
            nbits = 12
        elif protocol == "sirc15":
            protocol = "sony"
            nbits = 15
        elif protocol == "sirc20":
            protocol = "sony"
            nbits = 20
        elif protocol == "kaseikyo":
            protocol = "panasonic"
        elif protocol == "rc5x":
            protocol = "rc5"
        elif protocol in [
            "lg",
            "jvc",
            "sharp",
            "sanyo",
            "toshiba",
            "coolix",
            "whynter",
            "pioneer",
            "samsung36",
            "dish",
            "midea",
            "haier",
            "pronto",
            "rca",
        ]:
            protocol = protocol.lower()

        if btn_data.get("type", "").lower() == "raw":
            protocol = "raw"
        if protocol not in SUPPORTED_PROTOCOLS:
            self._skip_counts["unsupported_protocol"] += 1
            return

        payload: dict = {}
        if protocol == "raw":
            raw_str = btn_data.get("raw_data", "") or btn_data.get("data", "")
            try:
                payload["timings"] = [int(x) for x in raw_str.split()]
            except Exception:
                self._skip_counts["malformed_raw"] += 1
                return
            try:
                freq = int(btn_data["frequency"])
                if freq != 38000:
                    payload["frequency"] = freq
            except (KeyError, ValueError):
                pass
        else:
            if protocol == "samsung" and "data" not in btn_data and "address" in btn_data:
                addr = flipper_hex_to_int(btn_data.get("address", "0"))
                cmd = flipper_hex_to_int(btn_data.get("command", "0"))
                payload["data"] = f"0x{((addr << 24) | ((~addr & 0xFF) << 16) | (cmd << 8) | (~cmd & 0xFF)):X}"
                payload["nbits"] = 32
            else:
                if "address" in btn_data:
                    payload["address"] = parse_flipper_hex(btn_data["address"])
                if "command" in btn_data:
                    payload["command"] = parse_flipper_hex(btn_data["command"])
                if "data" in btn_data:
                    payload["data"] = parse_flipper_hex(btn_data["data"])
                if nbits:
                    payload["nbits"] = nbits

        buttons_list.append({"name": name, "icon": icon, "code": {"protocol": protocol, "payload": payload}})
