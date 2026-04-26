from unittest.mock import patch

from backend.models import IRCode
from backend.utils import match_ir_code, sanitize_topic_part


def test_match_ir_code_simple():
    stored_code = IRCode(protocol="NEC", payload={"address": "0x1234", "command": "0x5678"})

    # Exact match.
    received_code_match = {"protocol": "NEC", "payload": {"address": "0x1234", "command": "0x5678"}}
    assert match_ir_code(stored_code, received_code_match) is True

    # Partial match (extra fields in payload ignored).
    received_code_partial = {
        "protocol": "NEC",
        "payload": {"address": "0x1234", "command": "0x5678", "extra_field": "ignore"},
    }
    assert match_ir_code(stored_code, received_code_partial) is True

    # Mismatch protocol.
    received_code_proto_mismatch = {
        "protocol": "Sony",
        "payload": {"address": "0x1234", "command": "0x5678"},
    }
    assert match_ir_code(stored_code, received_code_proto_mismatch) is False

    # Mismatch command.
    received_code_cmd_mismatch = {
        "protocol": "NEC",
        "payload": {"address": "0x1234", "command": "0xABCD"},
    }
    assert match_ir_code(stored_code, received_code_cmd_mismatch) is False


def test_match_ir_code_raw_perfect_match():
    stored_code = IRCode(protocol="raw", payload={"timings": [100, -50, 100]})

    received_code_match_timings = {"protocol": "raw", "payload": {"timings": [100, -50, 100]}}
    assert match_ir_code(stored_code, received_code_match_timings) is True

    received_code_match_data = {"protocol": "raw", "payload": {"data": [100, -50, 100]}}
    assert match_ir_code(stored_code, received_code_match_data) is True


def test_match_ir_code_raw_tolerance_match():
    stored_code = IRCode(protocol="raw", payload={"timings": [1000, -500, 1000]}, raw_tolerance=20)

    received_within_tol = {"protocol": "raw", "payload": {"timings": [1100, -550, 950]}}
    assert match_ir_code(stored_code, received_within_tol) is True


def test_match_ir_code_raw_tolerance_fail():
    stored_code = IRCode(protocol="raw", payload={"timings": [1000, -500, 1000]}, raw_tolerance=20)

    received_outside_tol = {"protocol": "raw", "payload": {"timings": [1300, -500, 1000]}}
    assert match_ir_code(stored_code, received_outside_tol) is False

    received_sign_mismatch = {"protocol": "raw", "payload": {"timings": [1000, 500, 1000]}}
    assert match_ir_code(stored_code, received_sign_mismatch) is False

    received_len_mismatch = {"protocol": "raw", "payload": {"timings": [1000, -500]}}
    assert match_ir_code(stored_code, received_len_mismatch) is False


def test_match_ir_code_no_data():
    stored_code = IRCode(protocol="NEC", payload={"address": "0x1", "command": "0x2"})
    received_no_data = {}
    assert match_ir_code(stored_code, received_no_data) is False

    stored_raw_no_data = IRCode(protocol="raw")
    received_raw = {"protocol": "raw", "payload": {"data": "[100]"}}
    assert match_ir_code(stored_raw_no_data, received_raw) is False


def test_sanitize_topic_part():
    assert sanitize_topic_part("Living Room") == "living_room"
    assert sanitize_topic_part("Vol+") == "volplus"
    assert sanitize_topic_part("Ch#") == "chsharp"
    assert sanitize_topic_part("AC/DC") == "ac_dc"
    assert sanitize_topic_part("Back\\Slash") == "back_slash"
    assert sanitize_topic_part("Simple") == "simple"


def test_match_ir_code_raw_trailing_space_ignore():
    stored_code = IRCode(protocol="raw", payload={"timings": [1000, -1000]})

    received = {"protocol": "raw", "payload": {"timings": [1000, -5000]}}
    assert match_ir_code(stored_code, received) is True

    stored_code_pulse = IRCode(protocol="raw", payload={"timings": [1000, 1000]})
    received_pulse = {"protocol": "raw", "payload": {"timings": [1000, 5000]}}
    assert match_ir_code(stored_code_pulse, received_pulse) is False


def test_match_pronto():
    pronto_data = "0000 006D 0000 0000 0020 0020"
    stored = IRCode(protocol="pronto", payload={"data": pronto_data})

    received = {"protocol": "raw", "payload": {"data": [842, 842]}}
    assert match_ir_code(stored, received) is True

    received_bad = {"protocol": "raw", "payload": {"data": [2000, 2000]}}
    assert match_ir_code(stored, received_bad) is False

    stored_bad = IRCode(protocol="pronto", payload={"data": "invalid"})
    assert match_ir_code(stored_bad, received) is False


def test_atomic_write_yaml_error(tmp_path):
    from backend.utils import atomic_write_yaml

    target = tmp_path / "test.yaml"

    with patch("os.replace", side_effect=OSError("fail")):
        try:
            atomic_write_yaml(target, {"a": 1})
        except OSError:
            pass

    assert not target.exists()
