import asyncio
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query

from ..dependencies import (
    LoggerDep,
    MQTTManagerDep,
    StateManagerDep,
)
from ..loopback import run_loopback_test
from ..models import LoopbackTestResponse, StopLoopbackTestResponse

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api/test", tags=["diagnostics"])


@router.post("/loopback", response_model=LoopbackTestResponse)
async def start_loopback_test(
    state: StateManagerDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
    tx: str = Query(...),
    rx: str = Query(...),
    tx_channel: str | None = Query(None),
    rx_channel: str | None = Query(None),
    repeats: int = Query(3, ge=1, le=10),
    timeout: float = Query(3.0, ge=0.1, le=10.0),
    protocols: list[str] | None = Query(None),
):
    logger.info("Request to start loopback test from '%s' (channel: %s) to '%s' (channel: %s).", tx, tx_channel, rx, rx_channel)
    if tx not in mqtt.bridges:
        logger.error("Loopback test failed: TX bridge '%s' not found.", tx)
        raise HTTPException(404, f"Sender bridge '{tx}' not found")
    if rx not in mqtt.bridges:
        logger.error("Loopback test failed: RX bridge '%s' not found.", rx)
        raise HTTPException(404, f"Receiver bridge '{rx}' not found")

    state.test_task = asyncio.create_task(run_loopback_test(tx, rx, mqtt, state, tx_channel, rx_channel, repeats, timeout, protocols))
    logger.info("Loopback test from '%s' to '%s' started.", tx, rx)
    return LoopbackTestResponse(status="started", tx=tx, rx=rx)


@router.delete("/loopback", response_model=StopLoopbackTestResponse)
async def stop_loopback_test(
    state: StateManagerDep,
    logger: LoggerDep,
):
    if state.test_task and not state.test_task.done():
        state.test_task.cancel()
        logger.info("Loopback test stopped by user.")
    else:
        logger.info("Request to stop loopback test, but no active test found.")
    return StopLoopbackTestResponse()
