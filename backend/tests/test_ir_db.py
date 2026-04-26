from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.db.models import Base, IrDbButton, IrDbRemote
from backend.ir_db import IrDbManager


@asynccontextmanager
async def make_db_manager():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        with patch("backend.ir_db.get_session_maker", return_value=maker):
            manager = IrDbManager()
            manager.providers = []
            yield manager, maker
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_exists_empty():
    async with make_db_manager() as (manager, _):
        assert await manager.exists() is False


@pytest.mark.asyncio
async def test_exists_with_data():
    async with make_db_manager() as (manager, maker):
        async with maker() as session:
            async with session.begin():
                session.add(IrDbRemote(provider="flipper", path="flipper/LG/TV", name="TV"))
        assert await manager.exists() is True


@pytest.mark.asyncio
async def test_search():
    async with make_db_manager() as (manager, maker):
        async with maker() as session:
            async with session.begin():
                session.add(IrDbRemote(provider="flipper", path="flipper/Samsung/TV", name="Samsung TV"))
                session.add(IrDbRemote(provider="flipper", path="flipper/Sony/Audio", name="Sony Audio"))

        res = await manager.search("samsung")
        assert len(res) == 1
        assert res[0]["name"] == "Samsung TV"

        res = await manager.search("audio")
        assert len(res) == 1
        assert res[0]["name"] == "Sony Audio"

        res = await manager.search("nothing")
        assert len(res) == 0


@pytest.mark.asyncio
async def test_list_path_root():
    async with make_db_manager() as (manager, maker):
        mock_prov = MagicMock()
        mock_prov.id = "flipper"
        mock_prov.name = "Flipper"
        manager.providers = [mock_prov]

        async with maker() as session:
            async with session.begin():
                session.add(IrDbRemote(provider="flipper", path="flipper/LG/TV", name="TV"))

        items = await manager.list_path("")
        assert len(items) == 1
        assert items[0]["name"] == "Flipper"
        assert items[0]["type"] == "dir"


@pytest.mark.asyncio
async def test_list_path_subdir():
    async with make_db_manager() as (manager, maker):
        async with maker() as session:
            async with session.begin():
                session.add(IrDbRemote(provider="flipper", path="flipper/LG/TV", name="TV"))
                session.add(IrDbRemote(provider="flipper", path="flipper/LG/AC", name="AC"))
                session.add(IrDbRemote(provider="flipper", path="flipper/Sony/TV", name="TV"))

        items = await manager.list_path("flipper")
        assert len(items) == 2
        assert any(i["name"] == "LG" and i["type"] == "dir" for i in items)
        assert any(i["name"] == "Sony" and i["type"] == "dir" for i in items)


@pytest.mark.asyncio
async def test_list_path_files():
    async with make_db_manager() as (manager, maker):
        async with maker() as session:
            async with session.begin():
                session.add(IrDbRemote(provider="flipper", path="flipper/LG/TV", name="TV"))
                session.add(IrDbRemote(provider="flipper", path="flipper/LG/AC", name="AC"))

        items = await manager.list_path("flipper/LG")
        assert len(items) == 2
        assert all(i["type"] == "file" for i in items)
        assert any(i["name"] == "TV" for i in items)
        assert any(i["name"] == "AC" for i in items)


@pytest.mark.asyncio
async def test_get_stats():
    async with make_db_manager() as (manager, maker):
        async with maker() as session:
            async with session.begin():
                remote = IrDbRemote(provider="flipper", path="flipper/LG/TV", name="TV")
                session.add(remote)
                await session.flush()
                session.add(IrDbButton(remote_id=remote.id, name="Power", protocol="nec"))
                session.add(IrDbButton(remote_id=remote.id, name="Vol+", protocol="nec"))
                session.add(IrDbButton(remote_id=remote.id, name="Mute", protocol="sony"))

        stats = await manager.get_stats()
        assert stats["total_remotes"] == 1
        assert stats["total_codes"] == 3
        assert stats["protocols"]["nec"] == 2
        assert stats["protocols"]["sony"] == 1


@pytest.mark.asyncio
async def test_delete_db():
    async with make_db_manager() as (manager, maker):
        async with maker() as session:
            async with session.begin():
                session.add(IrDbRemote(provider="flipper", path="flipper/LG/TV", name="TV"))

        assert await manager.exists() is True
        await manager.delete_db()
        assert await manager.exists() is False


@pytest.mark.asyncio
async def test_parse_file():
    async with make_db_manager() as (manager, maker):
        async with maker() as session:
            async with session.begin():
                remote = IrDbRemote(provider="flipper", path="flipper/LG/TV", name="TV")
                session.add(remote)
                await session.flush()
                session.add(IrDbButton(remote_id=remote.id, name="Power", icon="power", protocol="nec", payload={"address": "0x1", "command": "0x2"}))

        buttons = await manager.parse_file("flipper/LG/TV")
        assert len(buttons) == 1
        assert buttons[0]["name"] == "Power"
        assert buttons[0]["code"]["protocol"] == "nec"


@pytest.mark.asyncio
async def test_irdb_update_logic():
    async with make_db_manager() as (manager, _):
        mock_prov = MagicMock()
        mock_prov.id = "flipper"
        mock_prov.name = "Flipper"
        mock_prov.download_and_convert = AsyncMock(
            return_value=[
                {
                    "path": "flipper/LG/TV",
                    "name": "TV",
                    "provider": "flipper",
                    "source_file": "TV.ir",
                    "buttons": [{"name": "Power", "icon": "power", "code": {"protocol": "nec", "payload": {"address": "0x1", "command": "0x2"}}}],
                }
            ]
        )
        manager.providers = [mock_prov]

        with patch("backend.websockets.broadcast_ws", new_callable=AsyncMock):
            await manager.update(flipper=True, probono=False)

        assert await manager.exists() is True
        stats = await manager.get_stats()
        assert stats["total_remotes"] == 1
        assert stats["total_codes"] == 1
