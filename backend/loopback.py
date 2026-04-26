import asyncio
import logging
import time

from .config import get_settings
from .models import BridgeSettings, IRCode
from .utils import match_ir_code
from .websockets import broadcast_ws

logger = logging.getLogger("ir2mqtt")

TEST_CASES = [
    {"protocol": "nec", "payload": {"address": "0x1", "command": "0xBF"}},
    {"protocol": "samsung", "payload": {"data": "0xE0E040BF", "nbits": 32}},
    {"protocol": "sony", "payload": {"data": "0xA90", "nbits": 12}},
    {"protocol": "panasonic", "payload": {"address": "0x4004", "command": "0x100BCBD"}},
    {"protocol": "rc5", "payload": {"address": "0x1", "command": "0x2"}},
    {"protocol": "rc6", "payload": {"address": "0x1", "command": "0x2"}},
    {"protocol": "jvc", "payload": {"data": "0xC5F8"}},
    {"protocol": "lg", "payload": {"data": "0x20DF10EF", "nbits": 32}},
    {"protocol": "coolix", "payload": {"first": "0xB27BE0", "second": "0xB27BE0"}},
    {"protocol": "pioneer", "payload": {"rc_code_1": "0xA55A", "rc_code_2": "0xA55A"}},
    {"protocol": "samsung36", "payload": {"address": "0x1", "command": "0x2"}},
    {"protocol": "dish", "payload": {"address": "0x1", "command": "0x2"}},
    {"protocol": "midea", "payload": {"data": [0xBA, 0x45, 0xD2, 0x2D, 0x0E, 0xF1]}},
    {"protocol": "haier", "payload": {"data": [0xA0] * 13}},
    {"protocol": "raw", "payload": {"timings": [4000, -4000, 1000, -1000, 1000, -1000, 1000, -1000]}},
    {"protocol": "aeha", "payload": {"address": "0x1234", "data": [0x12, 0x34]}},
    {"protocol": "abbwelcome", "payload": {"address": "0x1234", "command": "0x1"}},
    {"protocol": "beo4", "payload": {"command": "0x12", "source": "0x1"}},
    {"protocol": "byronsx", "payload": {"address": "0x1", "command": "0x1"}},
    {"protocol": "canalsat", "payload": {"device": "0x1", "command": "0x1"}},
    {"protocol": "canalsat_ld", "payload": {"device": "0x1", "command": "0x1"}},
    {"protocol": "dooya", "payload": {"address": "0x1234", "command": "0x1"}},
    {"protocol": "drayton", "payload": {"address": "0x1234", "command": "0x1"}},
    {"protocol": "dyson", "payload": {"address": "0x1234", "command": "0x1"}},
    {"protocol": "gobox", "payload": {"data": 1234}},
    {"protocol": "keeloq", "payload": {"encrypted": "0x12345678", "serial": "0x1234"}},
    {"protocol": "magiquest", "payload": {"id": "0x12345678", "magnitude": 123}},
    {"protocol": "mirage", "payload": {"data": [0x12, 0x34]}},
    {"protocol": "nexa", "payload": {"device": "0x12345678", "group": "0x1", "state": "0x1", "channel": "0x1", "level": "0x1"}},
    {"protocol": "rc_switch", "payload": {"code": "0x12345678", "protocol": 1}},
    {"protocol": "roomba", "payload": {"command": "0x1"}},
    {"protocol": "symphony", "payload": {"data": "0x123", "nbits": 12}},
    {"protocol": "toshiba_ac", "payload": {"rc_code_1": "0x12345678", "rc_code_2": "0x12345678"}},
    {"protocol": "toto", "payload": {"command": "0x1"}},
]


async def run_loopback_test(
    tx_bridge_id: str,
    rx_bridge_id: str,
    mqtt_manager,
    state_manager,
    tx_channel: str | None = None,
    rx_channel: str | None = None,
    repeats: int = 3,
    timeout: float = 3.0,
    protocols: list[str] | None = None,
):
    if state_manager.test_mode:
        logger.warning("Loopback test requested, but a test is already in progress.")
        return

    logger.info(
        "Starting loopback test. TX: '%s' (channel: %s), RX: '%s' (channel: %s), protocols: %s",
        tx_bridge_id,
        tx_channel or "any",
        rx_bridge_id,
        rx_channel or "any",
        protocols or "all common",
    )
    state_manager.test_mode = True
    state_manager.test_queue = asyncio.Queue()
    state_manager.test_rx_bridge = rx_bridge_id
    state_manager.test_rx_channel = rx_channel

    settings = get_settings()
    # Get capabilities
    tx_caps = set(mqtt_manager.bridges.get(tx_bridge_id, {}).get("capabilities", []))
    rx_caps = set(mqtt_manager.bridges.get(rx_bridge_id, {}).get("capabilities", []))
    logger.debug("TX capabilities: %s", tx_caps)
    logger.debug("RX capabilities: %s", rx_caps)

    common_protos = tx_caps.intersection(rx_caps)
    logger.info(
        "Found %d common protocols between bridges: %s",
        len(common_protos),
        common_protos,
    )

    if protocols:
        selected_protos = set(protocols)
        common_protos = common_protos.intersection(selected_protos)

    # Filter test cases
    active_test_cases = [c for c in TEST_CASES if c["protocol"] in common_protos]
    logger.info("Running %d test cases for the common protocols.", len(active_test_cases))

    # Backup protocols
    bridge_data = mqtt_manager.bridges.get(rx_bridge_id, {})
    original_protocols = bridge_data.get("enabled_protocols", [])
    logger.info("Backed up original RX bridge protocols: %s", original_protocols)

    # Backup Echo Settings
    rx_bridge_had_settings = rx_bridge_id in settings.bridge_settings
    original_echo_settings = None
    if rx_bridge_had_settings:
        original_echo_settings = settings.bridge_settings[rx_bridge_id].model_copy()

    # Disable Echo Suppression for RX bridge
    if not rx_bridge_had_settings:
        settings.bridge_settings[rx_bridge_id] = BridgeSettings()
    settings.bridge_settings[rx_bridge_id].echo_enabled = False
    logger.info("Temporarily disabled echo suppression on RX bridge '%s'.", rx_bridge_id)

    # Helper to update bridge
    async def update_bridge(protocols):
        logger.debug("Updating RX bridge '%s' to protocols: %s", rx_bridge_id, protocols)
        response = await mqtt_manager.bridge_manager.send_command(rx_bridge_id, "set_protocols", {"protocols": protocols})
        if response and response.get("success"):
            logger.debug("Successfully set protocols on bridge '%s'.", rx_bridge_id)
        else:
            logger.warning(
                "Failed to set protocols on bridge '%s'. Response: %s",
                rx_bridge_id,
                response,
            )

    try:
        # Notify start
        await broadcast_ws({"type": "test_start", "total": len(active_test_cases)})

        for idx, case in enumerate(active_test_cases):
            protocol = case["protocol"]
            logger.info(
                "--- Test Case %d/%d: %s ---",
                idx + 1,
                len(active_test_cases),
                protocol.upper(),
            )

            # Clear any stale messages from the receiver queue
            while not state_manager.test_queue.empty():
                try:
                    state_manager.test_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # Temporarily enable only this protocol
            logger.debug("Enabling only protocol '%s' on RX bridge.", protocol)
            await update_bridge([protocol])
            # Give bridge extra time on the first protocol to apply the new config
            await asyncio.sleep(1.0 if idx == 0 else 0.5)

            # Send `repeats` times
            logger.info("Sending IR code for protocol '%s' %d times...", protocol, repeats)
            logger.debug("Sent payload: %s", case)
            tx_target = f"{tx_bridge_id}:{tx_channel}" if tx_channel else tx_bridge_id
            for _ in range(repeats):
                await mqtt_manager.send_ir_code(case, target=tx_target)
                await asyncio.sleep(0.5)

            # Wait for receive
            try:
                start_time = time.time()
                matched = False
                received_data = None

                logger.debug("Waiting for code to be received...")
                # Wait up to `timeout` seconds for the code to come back
                while time.time() - start_time < timeout:
                    try:
                        received = await asyncio.wait_for(state_manager.test_queue.get(), timeout=timeout)
                        logger.debug("Received potential match: %s", received)
                        received_data = received

                        # Verify
                        stored_code = IRCode(**case)
                        if match_ir_code(stored_code, received):
                            matched = True
                            logger.info("Successfully matched received code.")
                            break
                        logger.warning("Received code did not match sent code.")
                    except TimeoutError:
                        logger.warning("Timed out waiting for a specific code.")
                        break

                status = "passed" if matched else "failed"
                logger.info("Test case for '%s' %s.", protocol, status.upper())
                result = {
                    "type": "test_progress",
                    "index": idx,
                    "protocol": protocol,
                    "sent": case,
                    "received": received_data,
                    "status": status,
                }
            except Exception as e:
                logger.error(
                    "An error occurred during test case for '%s': %s",
                    protocol,
                    e,
                    exc_info=True,
                )
                result = {
                    "type": "test_progress",
                    "index": idx,
                    "protocol": protocol,
                    "sent": case,
                    "received": None,
                    "status": "error",
                    "error": str(e),
                }

            await broadcast_ws(result)
            await asyncio.sleep(0.5)  # Delay between tests

        logger.info("All loopback test cases finished.")
        await broadcast_ws({"type": "test_end"})

    except asyncio.CancelledError:
        logger.info("Loopback test was cancelled by user.")
        await broadcast_ws({"type": "test_end"})
    except Exception as e:
        logger.error("An unhandled error occurred during the loopback test: %s", e, exc_info=True)
        await broadcast_ws({"type": "test_error", "message": str(e)})
    finally:
        logger.info("Restoring original RX bridge protocols...")
        # Restore protocols
        await update_bridge(original_protocols)
        logger.info("RX bridge protocols restored.")

        # Restore Echo Settings
        if rx_bridge_had_settings:
            settings.bridge_settings[rx_bridge_id] = original_echo_settings
        elif rx_bridge_id in settings.bridge_settings:
            del settings.bridge_settings[rx_bridge_id]
        logger.info("RX bridge echo settings restored.")

        state_manager.test_mode = False
        state_manager.test_queue = None
        state_manager.test_task = None
        state_manager.test_rx_bridge = None
        state_manager.test_rx_channel = None
        logger.info("Loopback test finished and state cleaned up.")
