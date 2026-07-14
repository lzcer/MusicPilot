# 1. MusicPilot Configuration Guide

This document explains the configuration steps required after starting MusicPilot for the first time. The recommended order is: prepare directories and environment variables first, then configure sites, downloaders, music libraries, system settings, and notifications in the Web UI.

## 1.1. Configuration Boundaries

MusicPilot has two types of configuration:

1. Startup configuration: set through environment variables or `.env`. These values decide how the service starts, where the database is stored, and how container directories are mounted.
2. Runtime configuration: saved to the database through the Web UI. This includes sites, downloaders, music library users, notification channels, proxy settings, scraping settings, and search settings.

In most cases, only deployment paths, the administrator account, the database URL, container volume paths, and the site parser file should be configured through environment variables. Site accounts, downloaders, music libraries, notifications, and scraping rules should be maintained in the Web UI.

## 1.2. Preparation Before First Startup

Using a published multi-architecture image is recommended. Docker Hub and GHCR contain the same image and version tags, so choose either registry based on network availability:

```yaml
# Docker Hub
image: lzcer/musicpilot:latest

# GHCR
image: ghcr.io/lzcer/musicpilot:latest
```

Both image sources support `linux/amd64` and `linux/arm64`.

Before deployment, confirm these directories:

| Directory | Purpose | Docker example |
| --- | --- | --- |
| Data directory | Stores the SQLite database, export/import files, and other runtime data. When PostgreSQL is used, it can still store local export files and related data. | `./data:/data` |
| Config directory | Stores custom site parser files and other configuration files. | `./config:/config` |
| Media root directory | Contains both the organized MusicPilot library and the qBittorrent download directory. | `/volume1/media:/media` |

The media root should contain the library and download directories:

```text
/volume1/media/music
/volume1/media/downloads
```

Mount the common parent once at `/media`, then use `/media/music` as the MusicPilot library and `/media/downloads` as the download directory. Mapped mode can create hardlinks only when the source and target are on the same filesystem and under the same container mount. A single physical disk, storage pool, or NAS volume does not guarantee this; separate mounts, filesystems, or Btrfs subvolumes cause hardlink creation to fail and MusicPilot to fall back to copying.

If qBittorrent and MusicPilot are not in the same container, or if they see different paths, configure both "download path" and "local path" in the downloader settings. For example, if qBittorrent saves files to `/media/downloads/music` and MusicPilot sees the same path in its container, both values can be the same. If qBittorrent reports the NAS path `/volume1/media/downloads/music` while MusicPilot sees `/media/downloads/music` inside the container, fill in those two paths separately.

## 1.3. Startup Environment Variables

Common environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `MP_APP_NAME` | `MusicPilot` | Application name. |
| `MP_LOG_LEVEL` | `INFO` | Log level. |
| `TZ` | `Asia/Shanghai` | Container time zone. Shanghai time is the default; change it for the deployment location if needed. |
| `MP_ADMIN_USERNAME` | `admin` | Administrator login username. |
| `MP_ADMIN_PASSWORD` | `musicpilot` | Administrator login password. Change this in production. |
| `MP_SESSION_SECRET` | `musicpilot-dev-session-secret` | Session secret. Change this to a long random string in production. |
| `MP_DATABASE_URL` | `sqlite+aiosqlite:///./data/musicpilot.db` | Database connection string. SQLite is fine for quick trials; PostgreSQL is recommended for long-running and production deployments. |
| `MP_HOST_MEDIA_PATH` | `./data/media` | Host media root used by Docker Compose. It should contain `music` and `downloads` subdirectories. |
| `MP_STATIC_DIR` | `frontend/dist` | Frontend static file directory. Container images usually use `/app/frontend/dist`. |
| `MP_SYSTEM_INDEXER_PARSER_CONFIG` | `config/sites.parser.yaml` | System site parser file. Usually does not need to be changed. |
| `MP_INDEXER_PARSER_CONFIG` | `config/sites.parser.yaml` | User custom site parser file. Docker deployments usually use `/config/sites.parser.yaml`. |
| `MP_RUNTIME_CONFIG` | `config/runtime.json` | Legacy runtime configuration migration entry. New configuration is stored in the database, so this file usually does not need manual editing. |
| `MP_MUSICBRAINZ_USER_AGENT` | `MusicPilot/0.1.0 (...)` | User-Agent used when accessing MusicBrainz. |
| `MP_WRITE_AUDIO_TAGS` | `true` | Whether to write audio tags. |
| `MP_SUBSCRIPTIONS_ENABLED` | `true` | Whether subscription checks are enabled. |
| `MP_SUBSCRIPTION_CHECK_INTERVAL_MINUTES` | `1440` | Subscription check interval in minutes. |

At minimum, change the administrator password and session secret in Docker Compose. SQLite can be used for a quick trial:

```yaml
environment:
  TZ: Asia/Shanghai
  MP_ADMIN_USERNAME: admin
  MP_ADMIN_PASSWORD: change-this-password
  MP_SESSION_SECRET: change-this-random-secret
  MP_DATABASE_URL: sqlite+aiosqlite:////data/musicpilot.db
  MP_INDEXER_PARSER_CONFIG: /config/sites.parser.yaml
volumes:
  - /volume1/media:/media
```

For an existing deployment that uses `MP_HOST_MUSIC_PATH` and `MP_HOST_DOWNLOADS_PATH`, place both directories under one host parent before replacing them with `MP_HOST_MEDIA_PATH`. Both new and existing deployments must configure the scraping source directory, mapped directory, and downloader local path in the Web UI. Changing mounts does not move existing files automatically.

## 1.4. Database Choice

MusicPilot supports SQLite and PostgreSQL. SQLite is simple to deploy and works well for local development, quick trials, or very small single-host setups. PostgreSQL is recommended for long-running and production deployments.

Reasons to prefer PostgreSQL:

1. Download polling, task queues, playlist sync, library refreshes, and log/status updates continuously write runtime data.
2. When multiple background tasks run at the same time, PostgreSQL handles concurrency and locking more reliably than SQLite.
3. Backup, recovery, migration, and observability are better suited to long-term maintenance.
4. If you later add more sites, playlists, and subscriptions, PostgreSQL is easier to scale with the growing data volume.

If PostgreSQL already exists, change `MP_DATABASE_URL` to:

```yaml
MP_DATABASE_URL: postgresql+asyncpg://musicpilot:change-this-password@postgres:5432/musicpilot
```

To run PostgreSQL in the same Docker Compose project, add a `postgres` service:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      TZ: Asia/Shanghai
      POSTGRES_DB: musicpilot
      POSTGRES_USER: musicpilot
      POSTGRES_PASSWORD: change-this-password
    volumes:
      - ./postgres:/var/lib/postgresql/data
    restart: unless-stopped

  musicpilot:
    environment:
      TZ: Asia/Shanghai
      MP_DATABASE_URL: postgresql+asyncpg://musicpilot:change-this-password@postgres:5432/musicpilot
    depends_on:
      - postgres
```

Do not reuse the example password in production. Before first startup, make sure the PostgreSQL data directory is persistent and include database backups in your normal backup plan.

## 2. Web UI Configuration Order

After logging in for the first time, open "System Management / Settings" and configure items in this order:

1. System settings: save proxy, scraping, and search parameters first.
2. Sites: add resource sites and confirm their parser support.
3. Downloaders: add qBittorrent and test the connection.
4. Music library: add Navidrome and test the connection.
5. Notifications: add Telegram notification channels as needed.
6. Playlists and subscriptions: import playlists or enable subscriptions after the base configuration works.

## 2.1. System Settings

System settings include network settings, scraping settings, search settings, and database management.

### 2.1.1. Network Settings

Network settings provide the system proxy, which is used by sites and notification channels that explicitly enable proxy usage.

| Field | Description |
| --- | --- |
| Proxy host | Can be `127.0.0.1`, `http://127.0.0.1:7890`, `socks5://127.0.0.1:7890`, and similar values. |
| Port | Fill this in when the proxy host does not include a port. |
| Username / password | Fill these in when the proxy requires authentication. |

If a site or notification channel has not enabled "use system proxy", saving the proxy settings will not affect it.

### 2.1.2. Scraping Settings

Scraping completes metadata, lyrics, tags, and target paths after downloads finish or when files are organized manually.

| Field | Options | Description |
| --- | --- | --- |
| Enable scraping | On / off | When disabled, automatic scraping will not run. |
| Scraping mode | Source file, mapped file, copied file | Controls where processed files come from and where they are written. |
| Source directory | Directory picker | Source directory used for manual organization. Available directories come from the filesystem visible to the MusicPilot runtime. |
| Mapped directory / copied directory | Directory picker | Required when "mapped file" or "copied file" is selected. Available directories come from the filesystem visible to the MusicPilot runtime. |
| Try scraping when missing | Album, artist, lyrics | Try online completion when these fields are missing. |
| Fail when missing | Album, artist, lyrics | If these fields are still missing, the organization task is treated as failed. |
| Auto rename | On / off | Rename files according to metadata. |
| Auto classify | On / off | Create classification directories by artist, album, or artist-album. |
| Classify by | Artist, album, artist-album | Applies when auto classify is enabled; artist-album saves files as `Artist/Album/Track`, using `Artist/Unknown Album/Track` when album metadata is missing. |
| Duplicate handling | Ignore, always overwrite, keep largest file | Decides what happens when the target file already exists. |

When "mapped file" is selected and no tags need to be written, MusicPilot tries to create a hardlink. The source and mapped directories must be under the same `/media` mount, and their host directories must not cross filesystems or Btrfs subvolumes. Otherwise MusicPilot falls back to copying and consumes additional disk space.

The directory picker can only browse paths that are already mounted and accessible to the MusicPilot process or container. It does not create directories or Docker mounts. Linux and Docker environments start at `/`; a direct Windows installation starts with the available drives and then navigates into directories.

Duplicate handling behavior:

1. `ignore`: skip when the target file already exists.
2. `overwrite`: overwrite when the target file already exists.
3. `keep_largest`: keep only the larger file.

### 2.1.3. Search Settings

| Field | Description |
| --- | --- |
| Exclude keywords | Separate multiple keywords with `|`. Site search results whose titles match any keyword will be filtered out. |
| Minimum seeders | Shows only torrents with at least this many seeders. Defaults to `1` to avoid dead torrents; set to `0` to disable this filter. |
| Metadata search concurrency | Limits how many metadata source search tasks can run at the same time. The default is `3`; reduce it to `1` or `2` if rate limits occur. |

## 2.2. Site Configuration

Site configuration stores resource site account information. MusicPilot currently supports NexusPHP-style sites, and a site must match a `base_url` in the parser configuration.

| Field | Description |
| --- | --- |
| Site name | Display name. |
| Site URL | Site root URL, for example `https://open.cd`. |
| Cookie | Cookie from a logged-in browser session. |
| User-Agent | User-Agent used when accessing the site. If the site has anti-bot checks, use the browser value. |
| Max concurrency | Per-site concurrent request limit, from `1` to `10`. |
| Enable site | When disabled, search will not use this site. |
| Use system proxy | When enabled, this site will use the system proxy. |

If saving a site reports "This site is not supported yet. Configure a parser in sites.parser.yaml first.", the site URL did not match any built-in or custom parser.

## 2.3. Site Parser Configuration

The site parser file describes how to extract titles, detail links, download links, size, publish time, and promotion information from a site's search result page. Docker deployments read this file by default:

```text
/config/sites.parser.yaml
```

The container image also includes a system parser configuration. On startup, MusicPilot reads the system parser first, then reads the user parser pointed to by `MP_INDEXER_PARSER_CONFIG`. If both files define the same site host, the user parser takes precedence.

Local development reads this file by default:

```text
config/sites.parser.yaml
```

One parser rule can be bound to multiple sites:

```yaml
sites:
  - targets:
      - name: OpenCD
        base_url: https://open.cd
      - name: HDFans
        base_url: https://hdfans.org/
    parser:
      list_selector: "table.torrents tr:has(a[href*='details.php']):has(a[href*='download.php'])"
      fields:
        title:
          selector: "a[href*='details.php']"
          filters: ["collapse_space"]
        details:
          selector: "a[href*='details.php']"
          attribute: "href"
        download:
          selector: "a[href*='download.php']"
          attribute: "href"
```

Common fields:

| Field | Description |
| --- | --- |
| `targets` | Site list that uses the same parser rule. |
| `parser.list_selector` | CSS selector for each torrent row in the search result list. |
| `parser.search_query_param` | Search keyword parameter name. The default is `search`. |
| `parser.search_params` | Fixed query parameters appended during search. |
| `parser.fields.title` | Torrent title. |
| `parser.fields.subtitle` | Subtitle or description. |
| `parser.fields.details` | Detail page URL. |
| `parser.fields.download` | Download URL. Required. |
| `parser.fields.size` | File size. |
| `parser.fields.published_at` | Publish time. |
| `parser.fields.promotion` | Freeleech, discount, or other promotion information. |
| `parser.fields.seeders` | Seeder count. |
| `parser.fields.leechers` | Leecher count. |
| `parser.filter` | Include or exclude parsed results. |

Field rules support:

| Config | Description |
| --- | --- |
| `selector` | CSS selector. |
| `attribute` | Attribute to read. Common values include `text`, `href`, `text+attrs`, and `titles`. |
| `regex` | Extracts a specific part from the read value. |
| `index` | Uses the Nth node when a selector matches multiple nodes. |
| `remove` | Removes specified content before extraction. |
| `filters` | Built-in filters, such as `collapse_space`, `category`, `date`, and `promotion`. |

After changing the parser file, restart the service or container so the parser is reloaded.

## 2.4. Downloader Configuration

The current downloader type is qBittorrent.

| Field | Description |
| --- | --- |
| Type | Fixed to `qbittorrent`. |
| Name | Display name. |
| URL | qBittorrent Web UI URL, for example `http://192.168.1.10:8080`. |
| Username / password | qBittorrent Web UI login credentials. |
| Download path | Save path submitted to qBittorrent. |
| Local path | Local or container path that MusicPilot uses to read downloaded files. |
| Listen mode | Currently uses polling. qB callback is reserved. |
| Set as default | Search results and playlist downloads are submitted to this downloader by default. |
| Enabled | When disabled, this downloader will not be used. |

Path examples:

| Scenario | Download path | Local path |
| --- | --- | --- |
| qBittorrent and MusicPilot see the same container path | `/media/downloads/music` | `/media/downloads/music` |
| qBittorrent returns a NAS host path, while MusicPilot reads inside a container | `/volume1/media/downloads/music` | `/media/downloads/music` |
| Windows local development | `D:\Downloads\music` | `D:\Downloads\music` |

The post-download organization flow depends on MusicPilot being able to access the "local path". If the connection test succeeds but MusicPilot cannot find files after download completion, check these two path values first.

## 2.5. Music Library Configuration

The current music library type is Navidrome. MusicPilot uses Navidrome to query the library, refresh the library, and sync local playlists to Navidrome.

| Field | Description |
| --- | --- |
| Type | Fixed to `navidrome`. |
| Name | Display name. |
| URL | Navidrome URL, for example `http://192.168.1.10:4533`. |
| API Token | Reserved field. Can be left empty. |
| Default username / default user password | Default account used to connect to Navidrome. |
| Enabled | When disabled, this music library will not be used. |

After saving the music library configuration, the page creates a default user account. If you need to sync playlists with different Navidrome users, add users under "User accounts". Edit the default account in the main music library configuration above.

Navidrome itself must also be able to scan the MusicPilot-organized music library directory. In Docker deployments, make Navidrome and MusicPilot use `/volume1/media/music` on the host; this directory is available to MusicPilot as `/media/music`.

## 2.6. Notification Configuration

The current notification type is Telegram.

| Field | Description |
| --- | --- |
| Type | Fixed to `telegram`. |
| Name | Display name. |
| Bot Token | Telegram Bot Token. |
| Webhook URL | Reserved or extension URL. Fill it according to your deployment if needed. |
| Chat IDs | Chat IDs that receive notifications. Fill multiple targets according to how your Bot is used. |
| Use system proxy | When enabled, notifications use the system proxy. |
| Download notifications | Whether to send download-related notifications. |
| Library refresh notifications | Whether to send library refresh notifications. |
| Enabled | When disabled, this channel will not send notifications. |

If Telegram cannot be reached directly from the deployment environment, save the proxy in system settings first, then enable "use system proxy" for this notification channel.

## 2.7. Database Import And Export

"System Settings / Database Management" provides database export and import.

1. Exporting the database generates a ZIP file for backup or migration.
2. Importing a database replaces current local data with the imported data. Export the existing database before importing.
3. After import, MusicPilot reloads site, downloader, and notification configuration.

## 3. Playlist Sync Configuration

Playlist features depend on base configuration:

1. At least one usable site is configured for resource search.
2. A default downloader is configured for download submission.
3. A usable Navidrome instance is configured for library refresh and playlist sync.
4. The music library has been scanned, so local tracks can be matched.

When syncing to Navidrome, you can choose the music library user and public status. MusicPilot builds playlists from persisted local library track IDs first, instead of rematching only by title.

## 4. FAQ

### 4.1. Saving A Site Reports It Is Unsupported

Check whether `sites.parser.yaml` contains a `base_url` with the same host. Matching ignores `www.`, but the protocol, host, and actual site should still match. After changing the parser, restart the service and save the site again.

### 4.2. Downloader Test Succeeds But Files Cannot Be Organized After Download

Check the downloader's "download path" and "local path". The first is the path qBittorrent sees when saving files; the second is the path MusicPilot sees when reading files. Container deployments often have mismatches between NAS paths and container mount paths.

### 4.3. Hardlink Creation Fails And Falls Back To Copying

If the UI reports that hardlink creation failed and copying was used instead, first confirm that the download and library directories are exposed through one common parent mounted at `/media`. Separate Docker mounts cannot create hardlinks between each other even when both host directories are on the same physical disk. Different filesystems or Btrfs subvolumes have the same limitation.

### 4.4. A Site Or Notification Channel Does Not Use The Proxy

After saving the system proxy, you still need to enable "use system proxy" on each site or notification channel. Configurations that do not enable it will not use the system proxy.

### 4.5. Navidrome Test Fails

Confirm that the Navidrome URL is reachable from the MusicPilot environment and that the username and password are correct. In container deployments, also confirm that the MusicPilot container can reach the Navidrome container or host network.

### 4.6. Scraping Results Are Missing Album, Artist, Or Lyrics

Check "try scraping when missing" and "fail when missing". If a field is set to "fail when missing" and online sources still do not provide it, the organization task will fail and record the reason.

### 4.7. Configuration Is Missing After Database Migration Or Moving Hosts

Confirm that you migrated the ZIP generated by "database export", or that you preserved the database file pointed to by `MP_DATABASE_URL`. Copying only `config/sites.parser.yaml` migrates site parsers only. It does not migrate sites, downloaders, music libraries, or notification configuration saved through the Web UI.
