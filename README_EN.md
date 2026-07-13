# MusicPilot

<p align="center">
  <img src="docs/assets/musicpilot-logo.png" alt="MusicPilot" width="420">
</p>

Language: [简体中文](README.md) | [English](README_EN.md)

## 1. Project Overview

MusicPilot is a self-hosted music library automation tool that turns music discovery, resource search, download submission, file organization, metadata completion, library refresh, and playlist sync into one manageable workflow.

It is designed for users who already run their own music library, downloader, and resource sites. MusicPilot does not replace those systems and does not provide download channels. Instead, it connects existing services and reduces repeated manual work around searching, downloading, organizing files, and refreshing the music library.

Core goals:

1. Provide one Web UI for managing music search, downloads, organization, playlists, and music library status.
2. Use a task queue to handle long-running operations, so downloads, scraping, organization, and sync can move forward automatically where possible.
3. Keep deployment simple. SQLite can be used for quick starts, while PostgreSQL is recommended for long-running and production deployments. Docker Compose is supported on NAS devices or servers.
4. Keep clear adapter boundaries so more sites, downloaders, music platforms, metadata sources, and media servers can be added later.

## 2. Supported Integrations

Media library support:

- [x] Navidrome

Downloader support:

- [x] qBittorrent
- [x] Transmission

Site support:

- [x] OpenCD
- [x] HDFans
- [x] HHClub
- [x] JPOP
- [x] ZMPT
- [x] Musopia
- [x] CarPT

## 3. Features

MusicPilot currently provides the following capabilities:

1. Music search and site search
   - Search music metadata first, then search candidate resources on configured sites based on that metadata.
   - Support site concurrency control, excluded keywords, and result deduplication.
   - Use artist, title, album, and related metadata to help filter candidate results.

2. Download task management
   - Submit selected resources to qBittorrent.
   - Track download status, view download details, and delete download tasks.
   - Trigger downstream organization and music library refresh flows after downloads complete.

3. File organization and metadata handling
   - Support source-directory, mapped-directory, and copy-based organization modes.
   - Support automatic scraping, manual organization, lyrics, and tag writing.
   - Record each file's organization status, failure reason, and actual organization type.

4. Playlist management
   - Import external playlists and manage playlist tracks locally.
   - Search, download, and match local library tracks from playlist entries.
   - Sync local playlists to a Navidrome music library, with selectable sync account and public/private status.

5. Music library and artist library
   - Scan and display music library tracks.
   - Maintain artists, aliases, and merge relationships to improve matching across Chinese names, English names, and aliases.
   - Refresh match status between playlists and the music library.

6. System management
   - Configure sites, downloaders, music libraries, notifications, and system parameters.
   - View logs, dashboard statistics, and file management pages.
   - Control basic deployment parameters through Docker environment variables.

## 4. Workflow

![MusicPilot workflow](docs/assets/musicpilot-workflow.png)

## 5. Screenshots

### 5.1. Dashboard

The dashboard summarizes library size, tracks added in the last 7 days, playlist count, active downloads, organization records, and task queue health. The recent downloads and recent organization sections make it easier to confirm whether automation is progressing normally and whether failed tasks need manual handling.

![MusicPilot dashboard](docs/assets/screenshots/dashboard.png)

### 5.2. Search and Site Selection

The search page shows music metadata candidates first, then asks the user to confirm which sites should be searched. The confirmation dialog keeps the media details and album list visible so the title, artist, and album clues can be checked before submitting a site search.

![MusicPilot search](docs/assets/screenshots/search.png)

### 5.3. Download Tasks

The downloads page shows submitted tasks with their status, progress, save path, and actions. Users can refresh task status, filter active tasks, open task details, or delete records that are no longer needed.

![MusicPilot downloads](docs/assets/screenshots/downloads.png)

### 5.4. File Management

The file management page is used to browse source files or target music library directories. It supports directory switching, file search, list refresh, batch organization, and deletion. Each file or directory keeps its type, size, modification time, and organization actions so users can manually intervene in the automated organization flow.

![MusicPilot media files](docs/assets/screenshots/media-files.png)

#### 5.4.1. Metadata Viewer

Audio files in File Management support on-demand metadata viewing. The detail dialog brings together the embedded cover, file information, title, artist, album, year, track number, duration, bitrate, sample rate, channels, and lyrics so the file can be checked before organization.

![MusicPilot metadata viewer](docs/assets/screenshots/media_info.png)

### 5.5. Playlist Management

The playlists page shows the local state of imported external playlists, including source platform, track count, existing tracks, pending tracks, submitted tasks, failures, and sync status. Public playlists from QQ Music, NetEase Cloud Music, Kuwo Music, Kugou Music, Spotify, and Apple Music can be imported from shared links. The action area provides entry points for details, match refresh, download submission, sync, and deletion.

![MusicPilot playlists](docs/assets/screenshots/playlists.png)

### 5.6. System Settings

The settings page groups runtime parameters by downloader, music library, notification, and system settings. System settings include proxy configuration, scraping switches, source directory, mapped directory, and missing-field handling, which control resource organization and metadata completion behavior.

![MusicPilot settings](docs/assets/screenshots/settings.png)

## 6. Quick Start

The following workflow is suitable for building and running MusicPilot directly from source on a NAS or server.

1. Clone the project and enter the directory:

```bash
git clone <your-repo-url> MusicPilot
cd MusicPilot
```

2. Update the key values in `docker-compose.yml`:

```yaml
ports:
  - "8000:8000"
volumes:
  - /volume1/docker/musicpilot/data:/data
  - /volume1/docker/musicpilot/config:/config
  - /volume1/music:/music
  - /volume1/downloads:/downloads
environment:
  TZ: Asia/Shanghai
  MP_ADMIN_USERNAME: admin
  MP_ADMIN_PASSWORD: change-this-password
  MP_SESSION_SECRET: change-this-random-secret
```

If the Docker build container cannot reach PyPI while the host network works normally, keep:

```yaml
build:
  network: host
```

If you need a more stable Python package mirror, adjust:

```yaml
build:
  args:
    UV_DEFAULT_INDEX: https://pypi.org/simple
```

3. Build and start the service:

```bash
docker compose up -d --build
```

4. Open the Web UI:

```text
http://<NAS_IP>:8000
```

5. View logs:

```bash
docker compose logs -f musicpilot
```

6. Update the project:

```bash
git pull
docker compose up -d --build
```

### 6.1. Recommended PostgreSQL Database

MusicPilot can start quickly with SQLite, but PostgreSQL is recommended for long-running and production deployments. Download polling, task queues, playlist sync, library refreshes, and database backups continuously write runtime data, and PostgreSQL is more reliable for concurrency, recovery, and maintenance.

If PostgreSQL already exists, change `MP_DATABASE_URL` in `docker-compose.yml` to a PostgreSQL connection string:

```yaml
MP_DATABASE_URL: postgresql+asyncpg://musicpilot:change-this-password@postgres:5432/musicpilot
```

Create the PostgreSQL database and user before starting MusicPilot. On startup, MusicPilot runs Alembic to initialize or upgrade the schema.

To run PostgreSQL in the same Compose project, add a `postgres` service and make MusicPilot depend on it:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: musicpilot
      POSTGRES_USER: musicpilot
      POSTGRES_PASSWORD: change-this-password
    volumes:
      - ./postgres:/var/lib/postgresql/data
    restart: unless-stopped

  musicpilot:
    environment:
      MP_DATABASE_URL: postgresql+asyncpg://musicpilot:change-this-password@postgres:5432/musicpilot
    depends_on:
      - postgres
```

### 6.2. Configuration Guide

After the first startup, configure sites, downloaders, music libraries, organization rules, and notification channels in the Web UI.

Configuration guide entry: [MusicPilot Configuration Guide](docs/configuration.en.md)

This document covers startup environment variables, site parsers, site accounts, downloaders, music libraries, scraping, search, notifications, and database backup steps.

## 7. Disclaimer

- This project is only a self-hosted music library organization and management tool. It does not directly provide, store, publish, or distribute any music resources, and it does not provide any download channels.
- This project only connects the media libraries, downloaders, sites, and metadata sources configured by users. Users must confirm the legality of their accounts, sites, resources, and files, and assume all responsibility for their own usage.
- This project is intended only for learning, discussion, and personal self-hosted usage. It must not be used for commercial purposes or any illegal activity.
- This project is open source. Any risks or liabilities caused by modification, redistribution, propagation, or removal of restrictions are the responsibility of the corresponding modifier, distributor, or user.
- This project does not accept donations, does not provide paid services, and does not publish any payment or donation entry anywhere. Please verify information carefully to avoid being misled.

## 8. Acknowledgements

MusicPilot's design and implementation reference many excellent open-source projects. Special thanks to:

1. [MoviePilot](https://github.com/jxxghp/MoviePilot)
   - MusicPilot is inspired by MoviePilot in self-hosted automation, task orchestration, site and downloader integration, and admin UI experience.

2. [musicdl](https://github.com/CharlesPikachu/musicdl)
   - MusicPilot's multi-source music metadata search and music information completion capabilities reference the practical work in musicdl around music platform data retrieval.

3. [Jackett/Jackett](https://github.com/Jackett/Jackett)
   - MusicPilot's site search integration references Jackett's approach to request parameters and result parsing rules for private trackers.

Thanks also to FastAPI, SQLAlchemy, Vue, Vite, Vuetify, qBittorrent, Navidrome, MusicBrainz, NexusPHP, and the broader open-source ecosystem for the foundational capabilities they provide.

This project is still evolving. Issues, discussions, and code contributions are welcome to help make it more stable and easier to use.
