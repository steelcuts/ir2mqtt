import os
from collections.abc import Callable

from sqlalchemy import select

from backend.config import get_settings
from backend.database import unit_of_work
from backend.db.models import IRAutomation as DBAutomation
from backend.db.session import init_db
from backend.models import IRAutomation, IRButton, IRDevice


class DeviceController:
    """
    Manages devices, buttons, and automations independently of the GUI.
    """

    def __init__(self, on_log: Callable[[str, str, str], None] | None = None):
        self.devices: list[IRDevice] = []
        self.automations: list[IRAutomation] = []
        self.on_log = on_log or (lambda src, msg, lvl: None)

    async def load_data(self, data_dir: str):
        # Set DB URL for backend modules
        db_path = os.path.join(data_dir, "ir2mqtt.db")
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

        # Force reload settings to pick up env vars if needed
        get_settings.cache_clear()

        await init_db()

        async with unit_of_work() as db:
            # Load Devices
            self.devices = await db.load_all_devices()

            # Load Automations
            stmt = select(DBAutomation).order_by(DBAutomation.ordering)
            result = await db.session.execute(stmt)
            db_automations = result.scalars().all()
            self.automations = [IRAutomation.model_validate(a) for a in db_automations]

    def find_device_and_button(self, dev_name: str, btn_name: str) -> tuple[IRDevice | None, IRButton | None]:
        for dev in self.devices:
            if dev.name.lower() == dev_name.lower():
                for btn in dev.buttons:
                    if btn.name.lower() == btn_name.lower():
                        return dev, btn
        return None, None

    def find_automation(self, name_or_id: str) -> IRAutomation | None:
        for auto in self.automations:
            if auto.id == name_or_id or auto.name.lower() == name_or_id.lower():
                return auto
        return None
