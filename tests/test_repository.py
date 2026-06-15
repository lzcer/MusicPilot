from pathlib import Path

from musicpilot.infra.db import Database, SqlAlchemyMediaRepository


async def test_default_media_server_falls_back_to_enabled_server(tmp_path: Path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'musicpilot.db'}")
    await database.create_all()
    repository = SqlAlchemyMediaRepository(database)
    try:
        server = await repository.upsert_media_server(
            payload={
                "name": "Navidrome",
                "type": "navidrome",
                "base_url": "https://music.local",
                "is_default": False,
                "enabled": True,
            }
        )

        default = await repository.default_media_server()

        assert default is not None
        assert default.id == server.id
    finally:
        await database.dispose()
