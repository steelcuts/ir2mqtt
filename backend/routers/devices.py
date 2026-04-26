import copy
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..dependencies import (
    AutomationManagerDep,
    DatabaseDep,
    LoggerDep,
    MQTTManagerDep,
    StateManagerDep,
)
from ..models import (
    AssignCodeResponse,
    DuplicateButtonResponse,
    DuplicateDeviceResponse,
    IRButton,
    IRButtonCreate,
    IRButtonUpdate,
    IRCode,
    IRDevice,
    IRDeviceCreate,
    IRDeviceUpdate,
    ReorderPayload,
    StatusOk,
    TriggerButtonResponse,
)
from ..websockets import broadcast_ws

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api", tags=["devices"])


class AssignCodePayload(BaseModel):
    code: IRCode | None = None


@router.get("/devices", response_model=list[IRDevice])
async def get_devices(db: DatabaseDep):
    return await db.load_all_devices()


@router.post("/devices", response_model=IRDevice)
async def add_device(
    device_in: IRDeviceCreate,
    db: DatabaseDep,
    mqtt: MQTTManagerDep,
    state: StateManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to add new device with name: '%s'", device_in.name)

    initial_buttons = []
    if device_in.buttons:
        for i, btn_data in enumerate(device_in.buttons):
            btn = IRButton(id=str(uuid.uuid4())[:8], ordering=i, **btn_data.model_dump())
            initial_buttons.append(btn)

    dev = IRDevice(
        id=str(uuid.uuid4())[:8],
        name=device_in.name,
        icon=device_in.icon,
        target_bridges=device_in.target_bridges,
        allowed_bridges=device_in.allowed_bridges,
        buttons=initial_buttons,
        ordering=len(state.devices),
    )

    await db.save_device(dev)
    await db.commit()
    state.devices.append(dev)
    await mqtt.integration.on_device_updated(dev, mqtt)
    await broadcast_ws({"type": "devices_updated"})
    logger.info("Successfully added new device '%s' with id %s.", dev.name, dev.id)
    return dev


@router.put("/devices/order", response_model=StatusOk)
async def reorder_devices(
    payload: ReorderPayload,
    db: DatabaseDep,
    state: StateManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to reorder devices.")
    await db.reorder_devices(payload.ids)
    await db.commit()

    # Sync state
    mapping = {d.id: d for d in state.devices}
    new_list = []
    for dev_id in payload.ids:
        if dev_id in mapping:
            new_list.append(mapping[dev_id])
    # Append any missing (safety fallback)
    existing_ids = set(payload.ids)
    new_list.extend([d for d in state.devices if d.id not in existing_ids])
    state.devices = new_list

    await broadcast_ws({"type": "devices_updated"})
    logger.info("Devices reordered successfully.")
    return StatusOk()


@router.put("/devices/{dev_id}", response_model=IRDevice)
async def update_device(
    dev_id: str,
    data: IRDeviceUpdate,
    db: DatabaseDep,
    state: StateManagerDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to update device %s.", dev_id)
    dev = await db.get_device(dev_id)
    if not dev:
        raise HTTPException(404, "Device not found")

    update_data = data.model_dump(exclude_unset=True)
    updated_device = dev.model_copy(update=update_data)

    await db.save_device(updated_device)
    await db.commit()

    # Sync state
    idx = next((i for i, d in enumerate(state.devices) if d.id == dev_id), -1)
    if idx != -1:
        state.devices[idx] = updated_device

    await mqtt.integration.on_device_updated(updated_device, mqtt)
    await broadcast_ws({"type": "devices_updated"})
    logger.info("Device %s ('%s') updated successfully.", dev_id, updated_device.name)
    return updated_device


@router.post("/devices/{dev_id}/duplicate", response_model=DuplicateDeviceResponse)
async def duplicate_device(
    dev_id: str,
    db: DatabaseDep,
    state: StateManagerDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to duplicate device %s.", dev_id)
    original_dev = await db.get_device(dev_id)
    if not original_dev:
        raise HTTPException(404, "Device not found")

    new_dev = copy.deepcopy(original_dev)
    new_dev.id = str(uuid.uuid4())[:8]

    new_name = f"{original_dev.name} (Copy)"
    counter = 1
    existing_names = {d.name.lower() for d in state.devices}
    while new_name.lower() in existing_names:
        counter += 1
        new_name = f"{original_dev.name} (Copy {counter})"

    new_dev.name = new_name

    for btn in new_dev.buttons:
        btn.id = str(uuid.uuid4())[:8]

    # Find the position of the original device
    idx = next((i for i, d in enumerate(state.devices) if d.id == dev_id), -1)
    if idx != -1:
        state.devices.insert(idx + 1, new_dev)
    else:
        state.devices.append(new_dev)

    # Set new explicit ordering values based on the state list
    for i, d in enumerate(state.devices):
        d.ordering = i

    await db.save_device(new_dev)
    await db.reorder_devices([d.id for d in state.devices])
    await db.commit()

    await mqtt.integration.on_device_updated(new_dev, mqtt)
    await broadcast_ws({"type": "devices_updated"})
    logger.info(
        "Device %s duplicated successfully as new device %s ('%s').",
        dev_id,
        new_dev.id,
        new_dev.name,
    )
    return DuplicateDeviceResponse(status="ok", device=new_dev)


@router.delete("/devices/{dev_id}", response_model=StatusOk)
async def del_device(
    dev_id: str,
    db: DatabaseDep,
    state: StateManagerDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to delete device %s.", dev_id)
    dev = await db.get_device(dev_id)
    if not dev:
        raise HTTPException(404, "Device not found")

    await mqtt.integration.on_device_deleted(dev, mqtt)
    await db.delete_device(dev_id)
    await db.commit()
    state.devices = [d for d in state.devices if d.id != dev_id]
    await broadcast_ws({"type": "devices_updated"})
    logger.info("Device %s deleted successfully.", dev_id)
    return StatusOk()


@router.put("/devices/{dev_id}/buttons/order", response_model=StatusOk)
async def reorder_buttons(
    dev_id: str,
    payload: ReorderPayload,
    state: StateManagerDep,
    db: DatabaseDep,
    logger: LoggerDep,
):
    logger.info("Request to reorder buttons for device %s.", dev_id)
    dev = await db.get_device(dev_id)
    if not dev:
        raise HTTPException(404, "Device not found")

    order = payload.ids
    mapping = {b.id: b for b in dev.buttons}
    new_list = [mapping[btn_id] for btn_id in order if btn_id in mapping]
    existing_ids = set(order)
    new_list.extend([b for b in dev.buttons if b.id not in existing_ids])

    for i, button in enumerate(new_list):
        button.ordering = i

    dev.buttons = new_list

    await db.save_device(dev)
    await db.commit()

    # Sync state
    state_dev = next((d for d in state.devices if d.id == dev_id), None)
    if state_dev:
        state_dev.buttons = new_list

    await broadcast_ws({"type": "devices_updated"})
    logger.info("Buttons for device %s reordered successfully.", dev_id)
    return StatusOk()


@router.post("/devices/{dev_id}/buttons", response_model=IRButton)
async def add_button(
    dev_id: str,
    btn_data: IRButtonCreate,
    state: StateManagerDep,
    db: DatabaseDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to add button to device %s.", dev_id)
    dev = await db.get_device(dev_id)
    if not dev:
        raise HTTPException(404, "Device not found")

    btn = IRButton(id=str(uuid.uuid4())[:8], **btn_data.model_dump())
    dev.buttons.append(btn)
    for i, b in enumerate(dev.buttons):
        b.ordering = i

    await db.save_device(dev)
    await db.commit()

    # Sync state
    state_dev = next((d for d in state.devices if d.id == dev_id), None)
    if state_dev:
        state_dev.buttons.append(btn)

    await mqtt.integration.on_device_updated(dev, mqtt)
    await broadcast_ws({"type": "devices_updated"})
    logger.info(
        "Button '%s' (%s) added to device %s ('%s').",
        btn.name,
        btn.id,
        dev_id,
        dev.name,
    )
    return btn


@router.put("/devices/{dev_id}/buttons/{btn_id}", response_model=IRButton)
async def update_button(
    dev_id: str,
    btn_id: str,
    btn_data: IRButtonUpdate,
    state: StateManagerDep,
    db: DatabaseDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to update button %s on device %s.", btn_id, dev_id)
    dev = await db.get_device(dev_id)
    if not dev:
        raise HTTPException(404, "Device not found")

    btn_idx = next((i for i, b in enumerate(dev.buttons) if b.id == btn_id), -1)
    if btn_idx == -1:
        raise HTTPException(404, "Button not found")

    update_data = btn_data.model_dump(exclude_unset=True)
    merged_data = dev.buttons[btn_idx].model_dump()
    merged_data.update(update_data)
    updated_button = IRButton.model_validate(merged_data)
    dev.buttons[btn_idx] = updated_button

    await db.save_device(dev)
    await db.commit()

    # Sync state
    state_dev = next((d for d in state.devices if d.id == dev_id), None)
    if state_dev:
        s_btn_idx = next((i for i, b in enumerate(state_dev.buttons) if b.id == btn_id), -1)
        if s_btn_idx != -1:
            state_dev.buttons[s_btn_idx] = updated_button

    await mqtt.integration.on_device_updated(dev, mqtt)
    await broadcast_ws({"type": "devices_updated"})
    logger.info("Button %s ('%s') on device %s updated.", btn_id, updated_button.name, dev_id)
    return updated_button


@router.delete("/devices/{dev_id}/buttons/{btn_id}", response_model=StatusOk)
async def del_button(
    dev_id: str,
    btn_id: str,
    state: StateManagerDep,
    db: DatabaseDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to delete button %s from device %s.", btn_id, dev_id)
    dev = await db.get_device(dev_id)
    if not dev:
        raise HTTPException(404, "Device not found")

    dev.buttons = [b for b in dev.buttons if b.id != btn_id]

    await db.save_device(dev)
    await db.commit()

    # Sync state
    state_dev = next((d for d in state.devices if d.id == dev_id), None)
    if state_dev:
        state_dev.buttons = [b for b in state_dev.buttons if b.id != btn_id]

    await mqtt.integration.on_device_updated(dev, mqtt)
    logger.info("Button %s from device %s deleted.", btn_id, dev_id)
    await broadcast_ws({"type": "devices_updated"})
    return StatusOk()


@router.post("/devices/{dev_id}/buttons/{btn_id}/duplicate", response_model=DuplicateButtonResponse)
async def duplicate_button(
    dev_id: str,
    btn_id: str,
    state: StateManagerDep,
    db: DatabaseDep,
    mqtt: MQTTManagerDep,
    logger: LoggerDep,
):
    logger.info("Request to duplicate button %s on device %s.", btn_id, dev_id)
    dev = await db.get_device(dev_id)
    if not dev:
        raise HTTPException(404, "Device not found")

    btn = next((b for b in dev.buttons if b.id == btn_id), None)
    if not btn:
        raise HTTPException(404, "Button not found")

    new_btn = copy.deepcopy(btn)
    new_btn.id = str(uuid.uuid4())[:8]

    new_name = f"{btn.name} (Copy)"
    counter = 1
    existing_names = {b.name.lower() for b in dev.buttons}
    while new_name.lower() in existing_names:
        counter += 1
        new_name = f"{btn.name} (Copy {counter})"

    new_btn.name = new_name

    try:
        idx = dev.buttons.index(btn)
        dev.buttons.insert(idx + 1, new_btn)
    except ValueError:
        dev.buttons.append(new_btn)

    for i, b in enumerate(dev.buttons):
        b.ordering = i

    await db.save_device(dev)
    await db.commit()

    # Sync state
    state_dev = next((d for d in state.devices if d.id == dev_id), None)
    if state_dev:
        try:
            s_idx = next(i for i, b in enumerate(state_dev.buttons) if b.id == btn_id)
            state_dev.buttons.insert(s_idx + 1, new_btn)
        except StopIteration:
            state_dev.buttons.append(new_btn)

        for i, b in enumerate(state_dev.buttons):
            b.ordering = i

    await mqtt.integration.on_device_updated(dev, mqtt)
    await broadcast_ws({"type": "devices_updated"})
    logger.info(
        "Button %s duplicated as new button %s ('%s') on device %s.",
        btn_id,
        new_btn.id,
        new_btn.name,
        dev_id,
    )
    return DuplicateButtonResponse(status="ok", button=new_btn)


@router.post("/devices/{dev_id}/buttons/{btn_id}/assign_code", response_model=AssignCodeResponse)
async def assign_last_code(
    dev_id: str,
    btn_id: str,
    state: StateManagerDep,
    db: DatabaseDep,
    logger: LoggerDep,
    payload: AssignCodePayload | None = None,
):
    logger.info("Request to assign code to button %s on device %s.", btn_id, dev_id)
    code_to_assign = payload.code if payload and payload.code else state.last_learned_code
    if not code_to_assign:
        raise HTTPException(400, "No code provided or learned recently.")

    dev = await db.get_device(dev_id)
    if not dev:
        raise HTTPException(404, "Device not found")

    btn = next((b for b in dev.buttons if b.id == btn_id), None)
    if not btn:
        raise HTTPException(404, "Button not found")

    btn.code = IRCode.model_validate(code_to_assign)

    await db.save_device(dev)
    await db.commit()

    # Sync state
    state_dev = next((d for d in state.devices if d.id == dev_id), None)
    if state_dev:
        state_btn = next((b for b in state_dev.buttons if b.id == btn_id), None)
        if state_btn:
            state_btn.code = btn.code

    logger.info("Assigned code to button '%s' on device '%s'.", btn.name, dev.name)
    state.last_learned_code = None
    await broadcast_ws({"type": "devices_updated"})
    await broadcast_ws({"type": "learning_status", "active": False, "code": None})
    return AssignCodeResponse()


@router.post("/devices/{dev_id}/buttons/{btn_id}/trigger", response_model=TriggerButtonResponse)
async def trigger_button(
    dev_id: str,
    btn_id: str,
    state: StateManagerDep,
    mqtt: MQTTManagerDep,
    automation_manager: AutomationManagerDep,
    logger: LoggerDep,
    targets: list[str] | None = Query(None),
):
    logger.info(
        "Request to trigger button %s on device %s with targets: %s.",
        btn_id,
        dev_id,
        targets or "device default",
    )
    dev_for_button = next((d for d in state.devices if d.id == dev_id), None)
    if not dev_for_button:
        raise HTTPException(404, "Device not found")

    btn_for_button = next((b for b in dev_for_button.buttons if b.id == btn_id), None)
    if not btn_for_button:
        raise HTTPException(404, "Button not found")

    if not btn_for_button.code:
        raise HTTPException(400, "Button has no code")

    final_targets = targets or dev_for_button.target_bridges

    if not final_targets:
        await mqtt.send_ir_code(btn_for_button.code.model_dump(exclude_none=True), target="broadcast")
    else:
        await mqtt.send_ir_code(btn_for_button.code.model_dump(exclude_none=True), target=final_targets)

    # Inform inactivity triggers that a code was manually sent to this device.
    await automation_manager.notify_device_activity(dev_id, btn_id, source="sent")

    await broadcast_ws({"type": "known_code_sent", "button_id": btn_id})
    return TriggerButtonResponse(status="sent", targets=final_targets or [])
