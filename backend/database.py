from __future__ import annotations

import logging
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from backend import models as pydantic_models
from backend.db import models as db_models
from backend.db.session import get_session_maker

logger = logging.getLogger(__name__)
Model = TypeVar("Model")


class DatabaseManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    def save(self, record: Model) -> Model:
        self.session.add(record)
        return record

    async def save_all(self, records: list[Model]) -> list[Model]:
        self.session.add_all(records)
        return records

    async def get_by_id(self, model: type[Model], record_id: str | int) -> Model | None:
        return await self.session.get(model, record_id)

    async def delete(self, record: Model):
        await self.session.delete(record)

    async def commit(self):
        await self.session.commit()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.close()

    async def load_all_devices(self):
        stmt = select(db_models.IRDevice).options(selectinload(db_models.IRDevice.buttons).selectinload(db_models.IRButton.code)).order_by(db_models.IRDevice.ordering)
        result = await self.session.execute(stmt)
        devices = result.scalars().all()
        return [pydantic_models.IRDevice.model_validate(d) for d in devices]

    async def get_device(self, device_id: str) -> pydantic_models.IRDevice | None:
        stmt = select(db_models.IRDevice).options(selectinload(db_models.IRDevice.buttons).selectinload(db_models.IRButton.code)).where(db_models.IRDevice.id == device_id)
        result = await self.session.execute(stmt)
        device = result.scalars().first()
        if device:
            return pydantic_models.IRDevice.model_validate(device)
        return None

    async def save_device(self, device: pydantic_models.IRDevice):
        # Use selectinload to avoid MissingGreenlet on lazy load of buttons
        stmt = select(db_models.IRDevice).options(selectinload(db_models.IRDevice.buttons).selectinload(db_models.IRButton.code)).where(db_models.IRDevice.id == device.id)
        result = await self.session.execute(stmt)
        db_device = result.scalars().first()

        if db_device:
            # Update existing device
            for key, value in device.model_dump(exclude={"buttons"}).items():
                setattr(db_device, key, value)

            # Update buttons (Merge strategy)
            existing_buttons = {b.id: b for b in db_device.buttons}
            new_buttons_list = []

            for button_model in device.buttons:
                if button_model.id in existing_buttons:
                    # Update existing button
                    db_btn = existing_buttons[button_model.id]
                    btn_data = button_model.model_dump(exclude={"code", "id"})
                    for k, v in btn_data.items():
                        setattr(db_btn, k, v)

                    self.session.add(db_btn)
                    # Update Code
                    if button_model.code:
                        if db_btn.code:
                            # Update existing code
                            code_data = button_model.code.model_dump()
                            for ck, cv in code_data.items():
                                setattr(db_btn.code, ck, cv)
                        else:
                            # Create new code
                            db_btn.code = db_models.IRCode(**button_model.code.model_dump())
                    else:
                        db_btn.code = None
                    new_buttons_list.append(db_btn)
                else:
                    # Create new button
                    new_button = db_models.IRButton(**button_model.model_dump(exclude={"code"}))
                    if button_model.code:
                        new_button.code = db_models.IRCode(**button_model.code.model_dump())
                    new_buttons_list.append(new_button)

            db_device.buttons = new_buttons_list
            self.session.add(db_device)
        else:
            # Create new device
            db_device = db_models.IRDevice(**device.model_dump(exclude={"buttons"}))
            for button_model in device.buttons:
                new_button = db_models.IRButton(**button_model.model_dump(exclude={"code"}))
                if button_model.code:
                    new_button.code = db_models.IRCode(**button_model.code.model_dump())
                db_device.buttons.append(new_button)
            self.save(db_device)

    async def delete_device(self, device_id: str):
        db_device = await self.get_by_id(db_models.IRDevice, device_id)
        if db_device:
            await self.delete(db_device)

    async def reorder_devices(self, device_ids: list[str]):
        for i, device_id in enumerate(device_ids):
            device = await self.get_by_id(db_models.IRDevice, device_id)
            if device:
                device.ordering = i

    async def delete_all_devices(self):
        await self.session.execute(db_models.IRCode.__table__.delete())
        await self.session.execute(db_models.IRButton.__table__.delete())
        await self.session.execute(db_models.IRDevice.__table__.delete())

    async def delete_all_automations(self):
        await self.session.execute(db_models.IRAutomation.__table__.delete())


def unit_of_work():
    session_maker = get_session_maker()
    return DatabaseManager(session_maker())


async def get_db():
    session_maker = get_session_maker()
    async with DatabaseManager(session_maker()) as db:
        yield db
