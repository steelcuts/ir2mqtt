import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

# Add the project root to the path.
current_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(os.path.dirname(current_dir)) == "backend":
    sys.path.insert(0, os.path.dirname(os.path.dirname(current_dir)))
else:
    sys.path.insert(0, os.path.dirname(current_dir))

from backend.db import session as db_session  # noqa: E402
from backend.main import app  # noqa: E402


@pytest.fixture(scope="function")
def client():
    with patch("backend.mqtt.MQTTManager.connect"):
        with TestClient(app) as c:
            yield c


@pytest.fixture(autouse=True)
def clean_overrides():
    yield
    app.dependency_overrides = {}


@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")


@pytest.fixture(autouse=True)
async def use_tmp_data_files(tmp_path):
    """Fixture to patch data file paths to use a temporary directory."""

    # Create a 'data' subdirectory in the tmp_path to mimic the real structure.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "ir_db").mkdir()

    from backend.config import get_settings

    get_settings.cache_clear()

    settings = get_settings()

    # Store original values
    orig_irdb = settings.irdb_path
    orig_opts = settings.options_file

    # Update settings
    settings.irdb_path = str(data_dir / "ir_db")
    settings.options_file = str(data_dir / "options.yaml")

    # Use a unique database file for this test run to avoid locking issues
    db_path = data_dir / "test.db"
    settings.database_url = f"sqlite+aiosqlite:///{db_path}"

    # Create new engine/session for this test
    new_engine = create_async_engine(settings.database_url, future=True, echo=False)

    # Reconfigure the existing sessionmaker to use the new engine.
    # This ensures that all modules holding a reference to db_session.async_session
    # (like backend.database and backend.main) use the new engine.
    if db_session.async_session is None:
        db_session.get_session_maker()
    db_session.async_session.configure(bind=new_engine)

    # Patch the db_session module's engine so init_db uses the new engine
    with patch.object(db_session, "engine", new_engine):
        yield

    await new_engine.dispose()

    # Restore settings
    settings.irdb_path = orig_irdb
    settings.options_file = orig_opts
    get_settings.cache_clear()


@pytest.fixture
def mqtt_manager(client):
    return app.state.mqtt_manager


@pytest.fixture
def automation_manager(client):
    return app.state.automation_manager


@pytest.fixture()
def reset_mqtt_integration(mqtt_manager):
    """Resets the global mqtt_manager integration to avoid test pollution."""
    yield
    mqtt_manager.integration = None


@pytest.fixture
def state_manager(client):
    return app.state.state_manager


@pytest.fixture()
def reset_automation_manager(automation_manager, mqtt_manager):
    """Resets the automation_manager state to avoid test pollution."""
    automation_manager.running_automations.clear()
    automation_manager.automations = []
    automation_manager.set_mqtt_manager(mqtt_manager)
    yield
    automation_manager.running_automations.clear()
