# MusicPilot

MusicPilot (MP) is a self-hosted automation hub for music discovery, download, metadata enrichment, library linking, and media-server refresh.

The project is designed around three constraints:

- **Async I/O first**: one Python process, pure async orchestration, low memory overhead, and high network/file-I/O concurrency.
- **Hexagonal architecture**: the core workflow depends on stable ports, while Telegram, Web UI, NexusPHP, qBittorrent, MusicBrainz, Navidrome, and future services live behind adapters.
- **Single artifact delivery**: the final deployment target is one Docker image containing the backend API and compiled Web UI.

`SPEC.md` is the source-of-truth architecture document for contributors and AI-assisted development. New modules should preserve its boundaries unless the spec is explicitly updated.

## 1. Current Structure

```text
musicpilot/
  core/        domain events, event bus, pipeline orchestration
  ports/       adapter protocols
  adapters/    external service implementations
  infra/       config, database, API, app bootstrap
frontend/      Vue/Vite management UI
alembic/       database migration scaffold
tests/         focused core tests
```

## 2. Implemented Modules

- Async event bus and core pipeline
- NexusPHP indexer loading from database sites and `config/sites.parser.yaml`
- qBittorrent download injection and completion webhook
- Download task polling and management
- Local file management and manual scrape/transfer
- Metadata cascade with multi-source provider
- Mutagen-based tag writer
- Navidrome/Subsonic library refresh and library sync
- Optional Telegram notification adapter
- Subscription persistence and APScheduler lifecycle
- Management UI with login, streaming search, downloads, media records, file management, logs, and settings
- FastAPI endpoints for health, search, downloads, media, files, indexers, subscriptions, and qBittorrent webhooks

## 3. NAS Docker Deployment

This mode builds the image directly on your NAS from the cloned repository. Docker Hub publishing is not required.

```bash
git clone <your-repo-url> MusicPilot
cd MusicPilot
cp .env.example .env
```

Edit `.env` before the first start:

```bash
MP_HTTP_PORT=8000
MP_ADMIN_USERNAME=admin
MP_ADMIN_PASSWORD=change-this-password
MP_SESSION_SECRET=change-this-random-secret
MP_HOST_MUSIC_PATH=/volume1/music
MP_HOST_DOWNLOADS_PATH=/volume1/downloads
```

Start the service:

```bash
docker compose up -d --build
```

Open the Web UI:

```text
http://<NAS_IP>:8000
```

View logs:

```bash
docker compose logs -f musicpilot
```

Stop the service:

```bash
docker compose down
```

Update from source:

```bash
git pull
docker compose up -d --build
```

## 4. Docker Volumes And Paths

The default `docker-compose.yml` mounts:

```text
./data                 -> /data
./config               -> /config
MP_HOST_MUSIC_PATH     -> /music
MP_HOST_DOWNLOADS_PATH -> /downloads
```

Important container paths:

```text
/data/musicpilot.db        SQLite database
/config/sites.parser.yaml  NexusPHP parser rules
/config/runtime.json       legacy runtime config migration source
/music                     music library path visible inside the container
/downloads                 download/source file path visible inside the container
```

For qBittorrent and MusicPilot to operate on the same files, configure paths consistently. For example, if qBittorrent saves music to `/volume1/downloads` on the NAS, mount that host path to `/downloads` and configure MusicPilot scraper source paths against `/downloads` inside the Web UI.

## 5. Development

Python 3.11+ is the target runtime.

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
uvicorn musicpilot.infra.api.app:create_app --factory --reload
```

Run tests:

```bash
pytest
```

With the included `Makefile`:

```bash
make install
make smoke
make dev
```

Verify the running backend:

```bash
curl --noproxy '*' http://127.0.0.1:8000/api/health
```

Run the frontend during development:

```bash
cd frontend
npm install
npm run dev
```

The default management login is controlled by:

```text
MP_ADMIN_USERNAME
MP_ADMIN_PASSWORD
```

## 6. API Surface

- `GET /api/health`
- `POST /api/search`
- `POST /api/downloads`
- `GET /api/downloads`
- `GET /api/files`
- `DELETE /api/files`
- `POST /api/files/organize`
- `POST /api/webhooks/qbittorrent/{torrent_hash}`
- `GET /api/indexers`
- `GET /api/media`
- `GET /api/subscriptions`
- `POST /api/subscriptions`

## 7. Configuration

MusicPilot reads environment variables with the `MP_` prefix.

```bash
MP_DATABASE_URL=sqlite+aiosqlite:///./data/musicpilot.db
MP_LOG_LEVEL=INFO
MP_MUSIC_LIBRARY_PATH=/music
MP_DOWNLOAD_STAGING_PATH=/downloads
MP_INDEXER_PARSER_CONFIG=/config/sites.parser.yaml
```

SQLite is the default database. The database layer enables WAL mode for SQLite and keeps model types portable for future PostgreSQL support.

## 8. License

GPL-3.0. See `LICENSE`.
