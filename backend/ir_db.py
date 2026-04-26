import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

from sqlalchemy import delete, func, insert, select

from .db.models import IrDbButton, IrDbRemote
from .db.session import get_session_maker
from .ir_base import IrRepoProvider

logger = logging.getLogger("ir2mqtt")


class IrDbManager:
    def __init__(self):
        self.providers: list[IrRepoProvider] = []
        self._load_providers()
        self._last_updated: int | None = None

    def _load_providers(self):
        providers_pkg = "backend.providers"
        providers_path = Path(__file__).parent / "providers"

        if not providers_path.exists():
            return

        for _, name, _ in pkgutil.iter_modules([str(providers_path)]):
            try:
                module = importlib.import_module(f"{providers_pkg}.{name}")
                for _, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, IrRepoProvider) and obj is not IrRepoProvider:
                        self.providers.append(obj())
            except Exception as e:
                logger.error("Failed to load provider %s: %s", name, e)

    def _session(self):
        return get_session_maker()()

    async def exists(self) -> bool:
        async with self._session() as session:
            count = await session.scalar(select(func.count(IrDbRemote.id)))
            return (count or 0) > 0

    async def get_stats(self) -> dict:
        async with self._session() as session:
            total_remotes = await session.scalar(select(func.count(IrDbRemote.id))) or 0
            total_codes = await session.scalar(select(func.count(IrDbButton.id))) or 0
            proto_rows = await session.execute(select(IrDbButton.protocol, func.count(IrDbButton.id)).group_by(IrDbButton.protocol))
            protocols = {row[0]: row[1] for row in proto_rows if row[0]}
        return {
            "total_remotes": total_remotes,
            "total_codes": total_codes,
            "protocols": protocols,
            "last_updated": self._last_updated,
        }

    async def delete_db(self):
        logger.info("Deleting IR database...")
        async with self._session() as session:
            async with session.begin():
                await session.execute(delete(IrDbRemote))
        self._last_updated = None
        logger.info("IR database deleted.")

    async def update(self, flipper: bool = True, probono: bool = True):
        from .websockets import broadcast_ws

        def get_provider(pid):
            return next((p for p in self.providers if p.id == pid), None)

        providers_to_update = []
        if flipper:
            p = get_provider("flipper")
            if p:
                providers_to_update.append(p)
        if probono:
            p = get_provider("probono")
            if p:
                providers_to_update.append(p)

        total_providers = len(providers_to_update)

        for i, p in enumerate(providers_to_update):

            async def wrapper(msg, idx=i):
                if msg.get("status") == "done":
                    return
                if "percent" in msg and msg["percent"] is not None:
                    msg["percent"] = int(((idx * 100) + msg["percent"]) / total_providers)
                await broadcast_ws(msg)

            remotes = await p.download_and_convert(wrapper)

            logger.info("[%s] Inserting %d remotes into database...", p.name, len(remotes))
            async with self._session() as session:
                async with session.begin():
                    # Remove existing entries for this provider
                    await session.execute(delete(IrDbRemote).where(IrDbRemote.provider == p.id))

                    if not remotes:
                        continue

                    # Bulk insert remotes
                    await session.execute(
                        insert(IrDbRemote),
                        [
                            {
                                "provider": r["provider"],
                                "path": r["path"],
                                "name": r["name"],
                                "source_file": r.get("source_file"),
                            }
                            for r in remotes
                        ],
                    )

                    # Build path → id mapping
                    paths = [r["path"] for r in remotes]
                    result = await session.execute(select(IrDbRemote.id, IrDbRemote.path).where(IrDbRemote.path.in_(paths)))
                    path_to_id = {row.path: row.id for row in result}

                    # Bulk insert buttons
                    button_rows = []
                    for remote in remotes:
                        remote_id = path_to_id.get(remote["path"])
                        if remote_id is None:
                            continue
                        for btn in remote.get("buttons", []):
                            code = btn.get("code", {})
                            button_rows.append(
                                {
                                    "remote_id": remote_id,
                                    "name": btn["name"],
                                    "icon": btn.get("icon"),
                                    "protocol": code.get("protocol"),
                                    "payload": code.get("payload", {}),
                                }
                            )

                    if button_rows:
                        await session.execute(insert(IrDbButton), button_rows)

            logger.info("[%s] Database insert complete.", p.name)

        import time

        self._last_updated = int(time.time() * 1000)
        await broadcast_ws({"type": "irdb_progress", "status": "done", "message": "Update complete."})

    async def search(self, query: str) -> list[dict]:
        if not query:
            return []

        tokens = query.lower().split()
        if not tokens:
            return []

        async with self._session() as session:
            stmt = select(IrDbRemote.path, IrDbRemote.name, IrDbRemote.provider)
            for token in tokens:
                pattern = f"%{token}%"
                stmt = stmt.where(func.lower(IrDbRemote.name).like(pattern) | func.lower(IrDbRemote.path).like(pattern))
            stmt = stmt.limit(100)
            rows = await session.execute(stmt)
            results = [{"path": r.path, "name": r.name, "provider": r.provider} for r in rows]

        q_lower = query.lower()
        results.sort(key=lambda x: 0 if x["name"].lower() == q_lower else (1 if x["name"].lower().startswith(q_lower) else 2))
        return results

    async def list_path(self, subpath: str = "") -> list[dict]:
        async with self._session() as session:
            if not subpath:
                rows = await session.execute(select(IrDbRemote.provider).distinct())
                providers_in_db = {r[0] for r in rows}
                return [{"name": p.name, "type": "dir", "path": p.id} for p in self.providers if p.id in providers_in_db]

            prefix = subpath.rstrip("/") + "/"
            rows = await session.execute(select(IrDbRemote.path, IrDbRemote.name).where(IrDbRemote.path.like(f"{prefix}%")))

            seen_dirs: set[str] = set()
            items: list[dict] = []
            for path, name in rows:
                rest = path[len(prefix) :]
                slash = rest.find("/")
                if slash == -1:
                    items.append({"name": name, "type": "file", "path": path})
                else:
                    dir_name = rest[:slash]
                    dir_path = prefix + dir_name
                    if dir_path not in seen_dirs:
                        seen_dirs.add(dir_path)
                        items.append({"name": dir_name, "type": "dir", "path": dir_path})

        items.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
        return items

    async def parse_file(self, subpath: str) -> list[dict]:
        async with self._session() as session:
            remote_id = await session.scalar(select(IrDbRemote.id).where(IrDbRemote.path == subpath))
            if remote_id is None:
                return []

            rows = await session.execute(select(IrDbButton).where(IrDbButton.remote_id == remote_id))
            buttons = []
            for (btn,) in rows:
                code = {"protocol": btn.protocol, "payload": btn.payload or {}}
                buttons.append({"name": btn.name, "icon": btn.icon, "code": code})
        return buttons
