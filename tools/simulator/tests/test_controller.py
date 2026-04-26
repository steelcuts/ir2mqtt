import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to the Python path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools", "simulator"))


from backend.models import IRAutomation, IRButton, IRCode, IRDevice  # noqa: E402
from tools.simulator.controller import DeviceController  # noqa: E402


@pytest.fixture
def controller():
    """Pytest fixture for the DeviceController."""
    return DeviceController()


@pytest.mark.asyncio
async def test_load_data(controller, tmp_path):
    """Test the load_data method."""
    db_path = tmp_path / "ir2mqtt.db"
    db_path.touch()

    mock_db = MagicMock()
    mock_db.load_all_devices = AsyncMock(return_value=[IRDevice(id="dev1", name="Device 1", buttons=[])])

    mock_automation = MagicMock()
    mock_automation.id = "auto1"
    mock_automation.name = "Automation 1"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_automation]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_db.session = mock_session

    with patch("tools.simulator.controller.init_db", new_callable=AsyncMock) as mock_init_db, patch("tools.simulator.controller.unit_of_work") as mock_unit_of_work:
        mock_unit_of_work.return_value.__aenter__.return_value = mock_db

        await controller.load_data(str(tmp_path))

        mock_init_db.assert_called_once()
        assert len(controller.devices) == 1
        assert controller.devices[0].name == "Device 1"
        assert len(controller.automations) == 1
        assert controller.automations[0].name == "Automation 1"


def test_find_device_and_button(controller):
    """Test the find_device_and_button method."""
    code = IRCode(protocol="nec", address="0x10", command="0x20")
    btn1 = IRButton(id="btn1", name="Button 1", code=code)
    dev1 = IRDevice(id="dev1", name="Device 1", buttons=[btn1])
    controller.devices = [dev1]

    # Test finding a device and button
    dev, btn = controller.find_device_and_button("Device 1", "Button 1")
    assert dev == dev1
    assert btn == btn1

    # Test case-insensitive finding
    dev, btn = controller.find_device_and_button("device 1", "button 1")
    assert dev == dev1
    assert btn == btn1

    # Test not found
    dev, btn = controller.find_device_and_button("Device 2", "Button 1")
    assert dev is None
    assert btn is None

    dev, btn = controller.find_device_and_button("Device 1", "Button 2")
    assert dev is None
    assert btn is None


def test_find_automation(controller):
    """Test the find_automation method."""
    auto1 = IRAutomation(id="auto1", name="Automation 1", triggers=[], actions=[])
    controller.automations = [auto1]

    # Test finding by name
    auto = controller.find_automation("Automation 1")
    assert auto == auto1

    # Test finding by id
    auto = controller.find_automation("auto1")
    assert auto == auto1

    # Test case-insensitive finding by name
    auto = controller.find_automation("automation 1")
    assert auto == auto1

    # Test not found
    auto = controller.find_automation("Automation 2")
    assert auto is None
