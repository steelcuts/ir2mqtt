import copy
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException

from ..dependencies import (
    AutomationManagerDep,
    LoggerDep,
    MQTTManagerDep,
)
from ..models import IRAutomation, ReorderPayload, StatusOk, TriggerAutomationResponse
from ..websockets import broadcast_ws

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api/automations", tags=["automations"])


@router.get("", response_model=list[IRAutomation])
async def get_automations(
    automation_manager: AutomationManagerDep,
    logger: LoggerDep,
):
    logger.debug("Request to get all automations.")
    return automation_manager.automations


@router.post("", response_model=IRAutomation)
async def add_automation(
    data: IRAutomation,
    automation_manager: AutomationManagerDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to add new automation.")
    if not data.id:
        data.id = str(uuid.uuid4())[:8]

    await automation_manager.add_automation(data)
    await mqtt.integration.on_automation_updated(data, mqtt)
    logger.info("New automation '%s' (%s) added.", data.name, data.id)
    await broadcast_ws({"type": "automations_updated"})
    return data


@router.put("/order", response_model=StatusOk)
async def reorder_automations(
    payload: ReorderPayload,
    automation_manager: AutomationManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to reorder automations.")
    await automation_manager.reorder(payload.ids)
    logger.info("Automations reordered successfully.")
    await broadcast_ws({"type": "automations_updated"})
    return StatusOk()


@router.put("/{auto_id}", response_model=IRAutomation)
async def update_automation(
    auto_id: str,
    data: IRAutomation,
    automation_manager: AutomationManagerDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to update automation %s.", auto_id)
    data.id = auto_id
    await automation_manager.update_automation(data)
    await mqtt.integration.on_automation_updated(data, mqtt)
    logger.info("Automation %s ('%s') updated.", auto_id, data.name)
    await broadcast_ws({"type": "automations_updated"})
    return data


@router.delete("/{auto_id}", response_model=StatusOk)
async def delete_automation(
    auto_id: str,
    automation_manager: AutomationManagerDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to delete automation %s.", auto_id)
    auto_to_delete = next((a for a in automation_manager.automations if a.id == auto_id), None)
    if auto_to_delete:
        await mqtt.integration.on_automation_deleted(auto_to_delete, mqtt)

    await automation_manager.delete_automation(auto_id)
    logger.info("Automation %s deleted.", auto_id)
    await broadcast_ws({"type": "automations_updated"})
    return StatusOk()


@router.post("/{auto_id}/duplicate", response_model=IRAutomation)
async def duplicate_automation(
    auto_id: str,
    automation_manager: AutomationManagerDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to duplicate automation %s.", auto_id)
    original_auto = next((a for a in automation_manager.automations if a.id == auto_id), None)

    if not original_auto:
        logger.error("Duplicate automation failed: Automation %s not found.", auto_id)
        raise HTTPException(404, "Automation not found")

    new_auto = copy.deepcopy(original_auto)
    new_auto.id = str(uuid.uuid4())[:8]

    new_name = f"{original_auto.name} (Copy)"
    counter = 1
    existing_names = {a.name.lower() for a in automation_manager.automations}
    while new_name.lower() in existing_names:
        counter += 1
        new_name = f"{original_auto.name} (Copy {counter})"

    new_auto.name = new_name
    new_auto.enabled = False
    new_auto.ha_expose_button = False

    await automation_manager.add_automation(new_auto)

    current_ids = [a.id for a in automation_manager.automations if a.id != new_auto.id]
    try:
        orig_idx = current_ids.index(auto_id)
        current_ids.insert(orig_idx + 1, new_auto.id)
    except ValueError:
        current_ids.append(new_auto.id)

    await automation_manager.reorder(current_ids)

    await mqtt.integration.on_automation_updated(new_auto, mqtt)
    logger.info(
        "Automation %s duplicated as new automation %s ('%s').",
        auto_id,
        new_auto.id,
        new_auto.name,
    )
    await broadcast_ws({"type": "automations_updated"})
    return new_auto


@router.post("/{auto_id}/trigger", response_model=TriggerAutomationResponse)
async def trigger_automation(
    auto_id: str,
    automation_manager: AutomationManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to trigger automation %s.", auto_id)
    auto = next((a for a in automation_manager.automations if a.id == auto_id), None)
    if not auto:
        logger.error("Trigger automation failed: Automation %s not found.", auto_id)
        raise HTTPException(404, "Automation not found")

    # trigger_from_ha will check if the automation is enabled
    await automation_manager.trigger_from_ha(auto_id, source="API")
    logger.info("Automation %s ('%s') triggered via API.", auto_id, auto.name)
    return TriggerAutomationResponse(status="ok", message=f"Automation '{auto.name}' triggered.")
