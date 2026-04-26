from pathlib import Path
from unittest.mock import mock_open, patch

from backend.providers.flipper import FlipperProvider
from backend.providers.probono import ProbonoProvider


def test_flipper_parse_ir_file():
    provider = FlipperProvider()

    # Mock file content.
    content = """
name: Power
type: parsed
protocol: NEC
address: 04 00 00 00
command: 02 00 00 00
# Comment
name: Vol+
type: parsed
protocol: NEC
address: 04 00 00 00
command: 03 00 00 00
"""
    with patch("builtins.open", mock_open(read_data=content)):
        buttons = provider._parse_ir_file(Path("dummy.ir"))

        assert len(buttons) == 2

        assert buttons[0]["name"] == "Power"
        assert buttons[0]["code"]["protocol"] == "nec"
        assert buttons[0]["code"]["payload"]["address"] == "0x4"
        assert buttons[0]["code"]["payload"]["command"] == "0x2"

        assert buttons[1]["name"] == "Vol Up"


def test_flipper_parse_raw():
    provider = FlipperProvider()
    content = """
name: RawBtn
type: raw
data: 100 200 100
"""
    with patch("builtins.open", mock_open(read_data=content)):
        buttons = provider._parse_ir_file(Path("dummy.ir"))
        assert len(buttons) == 1
        assert buttons[0]["code"]["protocol"] == "raw"
        assert buttons[0]["code"]["payload"]["timings"] == [100, 200, 100]


def test_probono_parse_csv(tmp_path):
    provider = ProbonoProvider()

    # Create real CSV file.
    d = tmp_path / "subdir"
    d.mkdir()
    p = d / "dummy.csv"
    content = "functionname,protocol,hex\nPower,NEC,0x1234\nVol+,RC5,0x5678"
    p.write_text(content)

    buttons = provider._parse_csv_file(p)

    assert len(buttons) == 2

    assert buttons[0]["name"] == "Power"
    assert buttons[0]["code"]["protocol"] == "nec"
    # 0x1234 -> addr 0x0, cmd 0x1234 for NEC in this provider logic if small.
    assert buttons[0]["code"]["payload"]["command"] == "0x1234"

    assert buttons[1]["name"] == "Vol Up"


def test_flipper_parse_raw_string_data():
    provider = FlipperProvider()
    content = """
name: Raw
type: raw
raw_data: 100 200
"""
    with patch("builtins.open", mock_open(read_data=content)):
        buttons = provider._parse_ir_file(Path("dummy.ir"))
        assert len(buttons) == 1
        assert buttons[0]["code"]["protocol"] == "raw"
        assert buttons[0]["code"]["payload"]["timings"] == [100, 200]


def test_probono_parse_csv_various_formats(tmp_path):
    provider = ProbonoProvider()

    d = tmp_path / "subdir"
    d.mkdir()
    p = d / "test.csv"

    # Test with device/function/subdevice format
    content = "functionname,protocol,device,subdevice,function\nPower,NEC,1,0,20"
    p.write_text(content)

    buttons = provider._parse_csv_file(p)
    assert len(buttons) == 1
    assert buttons[0]["name"] == "Power"
    assert buttons[0]["code"]["protocol"] == "nec"
    # NEC: device 1, sub 0, func 20 -> addr 0x1 (1<<8 | 0), cmd 0x14 (20)
    # Note: Probono logic for NEC: payload["address"] = f"0x{((d_val << 8) | s_val if s_val > 0 else d_val):X}"
    # d=1, s=0 -> s_val not > 0 -> d_val = 1 -> 0x1
    assert buttons[0]["code"]["payload"]["address"] == "0x1"
    assert buttons[0]["code"]["payload"]["command"] == "0x14"


def test_probono_convert(tmp_path):
    provider = ProbonoProvider()

    # Setup source structure
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    codes_dir = raw_root / "codes"
    codes_dir.mkdir()

    # Create a CSV file
    brand_dir = codes_dir / "brand"
    brand_dir.mkdir(parents=True, exist_ok=True)
    csv_file = brand_dir / "remote.csv"
    csv_file.write_text("functionname,protocol,hex\nPower,NEC,0x1234")

    # Create a non-CSV file (should be ignored)
    (brand_dir / "readme.txt").write_text("ignore")

    remotes = provider.convert(raw_root)

    assert len(remotes) == 1
    assert remotes[0]["name"] == "remote"
    assert remotes[0]["provider"] == "probono"
    assert len(remotes[0]["buttons"]) == 1
    assert remotes[0]["buttons"][0]["name"] == "Power"


def test_probono_convert_row_protocols():
    provider = ProbonoProvider()

    # Test Sony variants
    res = provider._convert_row("Btn", "sony12", "0x1", None, None, None)
    assert res["code"]["protocol"] == "sony"
    assert res["code"]["payload"]["nbits"] == 12

    res = provider._convert_row("Btn", "sony15", "0x1", None, None, None)
    assert res["code"]["protocol"] == "sony"
    assert res["code"]["payload"]["nbits"] == 15

    # Test unsupported protocol
    res = provider._convert_row("Btn", "unknown_proto", "0x1", None, None, None)
    assert res is None

    # Test hex parsing error
    res = provider._convert_row("Btn", "nec", "invalid_hex", None, None, None)
    assert res is None


def test_flipper_convert(tmp_path):
    provider = FlipperProvider()

    raw_root = tmp_path / "raw"
    raw_root.mkdir()

    # Create .ir file
    tv_dir = raw_root / "tv"
    tv_dir.mkdir(parents=True, exist_ok=True)
    ir_file = tv_dir / "remote.ir"
    ir_file.write_text("name: Power\ntype: parsed\nprotocol: NEC\naddress: 01 00 00 00\ncommand: 02 00 00 00")

    # Create ignored dir
    assets_dir = raw_root / "assets"
    assets_dir.mkdir()
    (assets_dir / "ignored.ir").write_text("content")

    remotes = provider.convert(raw_root)

    assert len(remotes) == 1
    assert remotes[0]["name"] == "remote"
    assert remotes[0]["path"] == "flipper/tv/remote"


def test_flipper_finalize_button_raw_error():
    provider = FlipperProvider()
    buttons = []
    btn_data = {
        "name": "Raw Error",
        "type": "raw",
        "protocol": "raw",
        "data": "this is not a list of numbers",
    }
    provider._finalize_button(btn_data, buttons)
    # The button should not be added if parsing fails
    assert len(buttons) == 0


def test_flipper_finalize_button_variants():
    provider = FlipperProvider()
    buttons = []

    # Samsung32
    provider._finalize_button(
        {
            "name": "Btn",
            "protocol": "samsung32",
            "address": "01 00 00 00",
            "command": "02 00 00 00",
        },
        buttons,
    )
    assert buttons[-1]["code"]["protocol"] == "samsung"
    assert buttons[-1]["code"]["payload"]["nbits"] == 32

    # Samsung address/command calculation logic (when data missing)
    provider._finalize_button(
        {
            "name": "Btn2",
            "protocol": "samsung",
            "address": "01 00 00 00",
            "command": "02 00 00 00",
        },
        buttons,
    )
    assert buttons[-1]["code"]["payload"]["data"] == "0x1FE02FD"

    # Raw with error
    provider._finalize_button({"name": "Btn3", "type": "raw", "raw_data": "invalid"}, buttons)
    assert len(buttons) == 2


def test_probono_convert_row_edge_cases():
    provider = ProbonoProvider()

    # Invalid Hex
    assert provider._convert_row("N", "nec", "zzzz") is None

    # Device/Function logic with invalid ints (should default to 0)
    # device="a", function="b" -> get_val returns 0
    res = provider._convert_row("N", "nec", None, device="a", function="b")
    # NEC: d=0, s=0, f=0 -> addr 0x0, cmd 0x0
    assert res["code"]["payload"]["address"] == "0x0"
    assert res["code"]["payload"]["command"] == "0x0"

    # Protocol specific logic
    # RC5: d=1, f=1 -> addr 0x1, cmd 0x1
    res = provider._convert_row("N", "rc5", None, device="1", function="1")
    assert res["code"]["payload"]["address"] == "0x1"
    assert res["code"]["payload"]["command"] == "0x1"

    # Sony 20 bit logic
    # d=1, s=1, f=1. 20bit: (f<<13)|(s<<5)|d = (1<<13)|(32)|1 = 8192+32+1 = 8225 = 0x2021
    res = provider._convert_row("N", "sony20", None, device="1", subdevice="1", function="1")
    assert res["code"]["payload"]["data"] == "0x2021"
