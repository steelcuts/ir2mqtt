from backend.ir_base import flipper_hex_to_int, parse_flipper_hex, standardize_ir_key


def test_standardize_ir_key_basics():
    cases = [
        ("POWER", "Power", "power"),
        ("pwr", "Power", "power"),
        ("vol+", "Vol Up", "volume-plus"),
        ("vol-", "Vol Down", "volume-minus"),
        ("ch+", "Ch Up", "television-shimmer"),
        ("ch-", "Ch Down", "television-shimmer"),
        ("mute", "Mute", "volume-mute"),
        ("1", "1", "numeric-1-box"),
        ("10", "10", "numeric-10-box-multiple-outline"),
        ("menu", "Menu", "menu"),
        ("up", "Up", "chevron-up"),
        ("down", "Down", "chevron-down"),
        ("left", "Left", "chevron-left"),
        ("right", "Right", "chevron-right"),
        ("ok", "OK", "check-circle-outline"),
        ("play", "Play", "play"),
        ("pause", "Pause", "pause"),
        ("stop", "Stop", "stop"),
        ("red", "Red", "button-cursor"),
        ("hdmi 1", "HDMI 1", "video-input-hdmi"),
        ("input", "Source", "import"),
    ]
    for raw, expected_name, expected_icon in cases:
        res = standardize_ir_key(raw)
        assert res["name"] == expected_name
        if expected_icon:
            assert res["icon"] == expected_icon


def test_standardize_ir_key_complex():
    # Test cleaning and fallback.
    res = standardize_ir_key("KEY_VOLUME_UP")
    assert res["name"] == "Vol Up"

    res = standardize_ir_key("btn_power_on")
    assert res["name"] == "Power On"

    res = standardize_ir_key("unknown_weird_key_name")
    assert res["name"] == "Unknown Weird Key Na"
    assert res["icon"] == "remote"

    res = standardize_ir_key("Volume V")
    assert res["name"] == "Vol Down"


def test_flipper_hex_parsing():
    # Little Endian conversion.
    # 04 00 00 00 -> 0x4
    assert parse_flipper_hex("04 00 00 00") == "0x4"
    assert flipper_hex_to_int("04 00 00 00") == 4

    # 10 00 00 00 -> 0x10 (16)
    assert parse_flipper_hex("10 00 00 00") == "0x10"

    # Invalid.
    assert parse_flipper_hex("invalid") == "invalid"
    assert flipper_hex_to_int("invalid") == 0
