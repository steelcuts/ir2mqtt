import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .models import IRCode

logger = logging.getLogger(__name__)


# --- UTILS ---
def _get_stored_raw(stored: IRCode) -> list[int] | None:
    p = stored.payload

    if stored.protocol == "raw":
        timings = p.get("timings")
        data = p.get("data")
        if timings and isinstance(timings, list):
            return timings
        if isinstance(data, list):
            return data
        return None

    if stored.protocol == "pronto":
        data = p.get("data")
        if not data or not isinstance(data, str):
            return None
        parts = [int(x, 16) for x in data.split()]
        if len(parts) < 4:
            return None
        frequency_divisor = parts[1]
        if frequency_divisor == 0:
            return None
        frequency = 1_000_000 / (frequency_divisor * 0.241246)
        time_base = 1_000_000.0 / frequency
        return [int(parts[i] * time_base) for i in range(4, len(parts))]

    return None


def _match_raw_pronto(stored: IRCode, received: dict[str, Any]) -> bool:
    try:
        stored_raw = _get_stored_raw(stored)
        if stored_raw is None:
            return False

        received_payload = received.get("payload") or {}
        received_data = received_payload.get("timings") or received_payload.get("data")
        if isinstance(received_data, str):
            received_raw = json.loads(received_data)
        elif isinstance(received_data, list):
            received_raw = received_data
        else:
            return False

        if len(stored_raw) != len(received_raw):
            return False

        tolerance_pct = (stored.raw_tolerance or 20) / 100.0

        for i, (s, r) in enumerate(zip(stored_raw, received_raw)):
            if (s >= 0 > r) or (s < 0 <= r):
                return False

            # Ignore tolerance for the last element if it is a space (negative)
            if i == len(stored_raw) - 1 and s < 0:
                continue

            if abs(s - r) > abs(s) * tolerance_pct:
                return False

        return True
    except Exception:
        return False


def match_ir_code(stored: IRCode, received: dict[str, Any]) -> bool:
    """Compares a stored IRCode with a received dictionary, handling raw/pronto tolerance."""
    if stored.protocol != received.get("protocol"):
        # Allow a received 'raw' to be matched against a stored 'pronto'
        if not (stored.protocol == "pronto" and received.get("protocol") == "raw"):
            return False

    if stored.protocol in ["raw", "pronto"]:
        return _match_raw_pronto(stored, received)

    received_payload = received.get("payload") or {}
    for k, v in (stored.payload or {}).items():
        recv_v = received_payload.get(k)
        if recv_v == v:
            continue
        if isinstance(v, str) and isinstance(recv_v, str) and v.lower() == recv_v.lower():
            continue
        return False

    return True


def sanitize_topic_part(name: str) -> str:
    return name.lower().replace(" ", "_").replace("+", "plus").replace("#", "sharp").replace("/", "_").replace("\\", "_")


def atomic_write_yaml(filepath: str | Path, data: Any):
    """Writes YAML data to a file atomically to prevent corruption."""
    filepath_str = str(filepath)
    dir_name = os.path.dirname(filepath_str)

    if not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tmp_file:
        yaml.safe_dump(data, tmp_file, default_flow_style=False, sort_keys=False)
        tmp_path = tmp_file.name
        tmp_file.flush()
        os.fsync(tmp_file.fileno())

    try:
        os.replace(tmp_path, filepath_str)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise e


def load_options(options_file: str) -> dict[str, Any]:
    options = {}
    if os.path.exists(options_file):
        try:
            with open(options_file, encoding="utf-8") as f:
                options = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error("Failed to load options file %s: %s", options_file, e, exc_info=True)
    return options


def update_options_file(options_file: str, updates: dict[str, Any]):
    options = load_options(options_file)
    options.update(updates)
    atomic_write_yaml(options_file, options)
