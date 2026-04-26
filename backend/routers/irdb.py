from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..dependencies import (
    IrDbManagerDep,
    LoggerDep,
    MQTTManagerDep,
    StateManagerDep,
)
from ..models import (
    CancelLearningResponse,
    IRCode,
    IrDbBrowseResponse,
    IrDbSearchResponse,
    IrDbStatusResponse,
    SendIrDbCodeResponse,
    StartLearningResponse,
    StatusOk,
)
from ..websockets import broadcast_ws

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api", tags=["irdb"])


class IrdbUpdatePayload(BaseModel):
    flipper: bool = True
    probono: bool = True


class SendCodePayload(BaseModel):
    code: IRCode
    target: list[str] | str | None = None


@router.get("/irdb/status", response_model=IrDbStatusResponse)
async def get_irdb_status(irdb_manager: IrDbManagerDep):
    exists = await irdb_manager.exists()
    stats = await irdb_manager.get_stats()
    return {"exists": exists, **stats}


@router.post("/irdb/sync", response_model=StatusOk)
async def update_irdb(
    payload: IrdbUpdatePayload,
    irdb_manager: IrDbManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to update IRDB...")
    try:
        await irdb_manager.update(flipper=payload.flipper, probono=payload.probono)
        logger.info("IRDB update completed successfully.")
        return StatusOk()
    except Exception as e:
        logger.error("Failed to update IRDB: %s", e, exc_info=True)
        raise HTTPException(500, f"Update failed: {str(e)}") from e


@router.get("/irdb/browse", response_model=list[IrDbBrowseResponse])
async def browse_irdb(
    irdb_manager: IrDbManagerDep,
    logger: LoggerDep,
    path: str = "",
):
    logger.debug("Browsing IRDB path: '%s'", path)
    return await irdb_manager.list_path(path)


@router.get("/irdb/search", response_model=list[IrDbSearchResponse])
async def search_irdb(
    q: str,
    irdb_manager: IrDbManagerDep,
    logger: LoggerDep,
):
    logger.debug("Searching IRDB for: '%s'", q)
    return await irdb_manager.search(q)


@router.get("/irdb/file")
async def load_irdb_file(
    path: str,
    irdb_manager: IrDbManagerDep,
    logger: LoggerDep,
):
    logger.debug("Loading IRDB file: '%s'", path)
    return await irdb_manager.parse_file(path)


@router.post("/irdb/send_code", response_model=SendIrDbCodeResponse)
async def send_irdb_code(
    payload: SendCodePayload,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    """Sends a raw IR code, for testing from the IRDB."""
    logger.info("Request to send IRDB code to targets '%s'.", payload.target or "broadcast")
    await mqtt.send_ir_code(payload.code.model_dump(), target=payload.target)
    targets = payload.target if isinstance(payload.target, list) else ([payload.target] if payload.target else [])
    return SendIrDbCodeResponse(targets=targets)


@router.post("/learn", response_model=StartLearningResponse)
async def start_learning(
    state: StateManagerDep,
    logger: LoggerDep,
    bridges: list[str] = Query(["any"]),
    smart: bool = Query(False),
):
    """Start learning mode. Target a specific bridge name, or 'any' for all."""

    state.learning_bridges = bridges
    state.learning_type = "smart" if smart else "simple"
    state.smart_samples = []
    state.current_burst = []
    if state.burst_timer:
        state.burst_timer.cancel()
        state.burst_timer = None
    state.last_learned_code = None

    logger.info(
        "IR learning mode activated (type: %s, bridges: '%s').",
        state.learning_type,
        bridges,
    )
    await broadcast_ws(
        {
            "type": "learning_status",
            "active": True,
            "bridges": bridges,
            "mode": state.learning_type,
        }
    )
    return StartLearningResponse(bridges=bridges, mode=state.learning_type)


@router.post("/learn/cancel", response_model=CancelLearningResponse)
async def cancel_learning(
    state: StateManagerDep,
    logger: LoggerDep,
):
    state.learning_bridges = []
    logger.info("IR learning mode cancelled by user.")
    await broadcast_ws({"type": "learning_status", "active": False})
    return CancelLearningResponse()
