import csv
import os
from pathlib import Path

from ..ir_base import SUPPORTED_PROTOCOLS, IrRepoProvider, standardize_ir_key


class ProbonoProvider(IrRepoProvider):
    def __init__(self):
        super().__init__(
            id="probono",
            name="Probono IRDB",
            url="https://github.com/probonopd/irdb/archive/refs/heads/master.zip",
        )

    def convert(self, raw_root: Path) -> list[dict]:
        remotes = []
        start_dir = raw_root / "codes" if (raw_root / "codes").exists() else raw_root

        for root, dirs, files in os.walk(start_dir):
            for file in files:
                if not file.endswith(".csv"):
                    continue

                source_file = Path(root) / file
                rel_path = source_file.relative_to(start_dir)

                buttons = self._parse_csv_file(source_file)
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
        return remotes

    def _parse_csv_file(self, path: Path) -> list[dict]:
        buttons = []
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                sample = f.read(2048)
                f.seek(0)
                delimiter = ";" if ";" in sample and sample.count(";") > sample.count(",") else ","
                reader = csv.DictReader(f, delimiter=delimiter)
                if reader.fieldnames:
                    reader.fieldnames = [fn.lower().strip() if fn else "" for fn in reader.fieldnames]

                for row in reader:
                    name = row.get("functionname") or row.get("key") or row.get("name") or row.get("button")
                    protocol = row.get("protocol") or row.get("proto")
                    hex_code = row.get("hex") or row.get("scancode") or row.get("code") or row.get("data")
                    device = row.get("device")
                    subdevice = row.get("subdevice")
                    function = row.get("function")

                    if name and protocol:
                        btn = self._convert_row(name, protocol, hex_code, device, subdevice, function)
                        if btn:
                            buttons.append(btn)
        except Exception:
            pass
        return buttons

    def _convert_row(
        self,
        name: str,
        protocol: str,
        hex_code: str | None,
        device: str | None = None,
        subdevice: str | None = None,
        function: str | None = None,
    ) -> dict | None:
        std = standardize_ir_key(name)
        name = std["name"]
        icon = std["icon"]
        protocol = protocol.lower().strip()
        nbits = None

        if protocol in ["nec", "nec1", "nec2", "necx1", "necx2", "apple"]:
            protocol = "nec"
        elif protocol in ["rc5", "rc5-7f"]:
            protocol = "rc5"
        elif protocol in ["rc6", "rc6-0-16", "rc6-6-20"]:
            protocol = "rc6"
        elif protocol == "sony12":
            protocol = "sony"
            nbits = 12
        elif protocol == "sony15":
            protocol = "sony"
            nbits = 15
        elif protocol == "sony20":
            protocol = "sony"
            nbits = 20
        elif protocol in ["jvc", "jvc-48", "jvc{2}"]:
            protocol = "jvc"
        elif protocol in ["samsung36"]:
            protocol = "samsung36"
        elif protocol in ["sharp", "sharp{1}", "sharp{2}", "sharpdvd"]:
            protocol = "sharp"
        elif protocol in ["rca", "rca-38", "rca(old)"]:
            protocol = "rca"
        elif protocol in ["dish_network", "dishplayer"]:
            protocol = "dish"
        elif protocol in ["pioneer"]:
            protocol = "pioneer"
        elif protocol in ["panasonic", "panasonic2", "panasonic_old"]:
            protocol = "panasonic"

        if protocol not in SUPPORTED_PROTOCOLS:
            return None
        payload: dict = {}

        if hex_code:
            try:
                hex_code = hex_code.replace("0x", "").replace(" ", "").strip()
                val = int(hex_code, 16)
                if protocol in ["nec", "rc5", "rc6", "panasonic"]:
                    if val > 0xFFFF:
                        payload["address"] = f"0x{((val >> 16) & 0xFFFF):X}"
                        payload["command"] = f"0x{(val & 0xFFFF):X}"
                    else:
                        payload["address"] = "0x0"
                        payload["command"] = f"0x{val:X}"
                else:
                    payload["data"] = f"0x{val:X}"
                    if nbits is not None:
                        payload["nbits"] = nbits
            except ValueError:
                return None
        elif device and function:
            try:

                def get_val(v):
                    try:
                        i = int(v)
                        return i if i != -1 else 0
                    except (ValueError, TypeError):
                        return 0

                d_val, s_val, f_val = (
                    get_val(device),
                    get_val(subdevice),
                    get_val(function),
                )

                if protocol == "nec":
                    if s_val > 0:
                        address_val = (d_val << 8) | s_val
                    else:
                        address_val = d_val
                    payload["address"] = f"0x{address_val:X}"
                    payload["command"] = f"0x{f_val:X}"
                elif protocol == "sony":
                    if nbits == 20:
                        data_val = (f_val << 13) | (s_val << 5) | d_val
                    else:
                        shift = 8 if nbits == 15 else 5
                        data_val = (f_val << shift) | d_val
                    payload["data"] = f"0x{data_val:X}"
                    payload["nbits"] = nbits
                elif protocol == "jvc":
                    payload["data"] = f"0x{(f_val | (d_val << 8)):X}"
                elif protocol in [
                    "rc5",
                    "rc6",
                    "sharp",
                    "rca",
                    "pioneer",
                    "dish",
                    "samsung36",
                    "panasonic",
                ]:
                    payload["address"] = f"0x{d_val:X}"
                    payload["command"] = f"0x{f_val:X}"
                else:
                    return None
            except ValueError:
                return None
        else:
            return None

        return {"name": name, "icon": icon, "code": {"protocol": protocol, "payload": payload}}
