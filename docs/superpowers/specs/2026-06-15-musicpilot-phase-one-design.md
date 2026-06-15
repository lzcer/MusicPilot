# MusicPilot Phase One Search and Download Workflow Design

Date: 2026-06-15

## Goal

Phase one changes MusicPilot from direct site search to a two-step music metadata search and confirmed site search workflow. It also moves runtime business configuration into the database and introduces a persistent download task state machine.

The MVP must complete this loop:

1. Search metadata candidates.
2. Let the user choose a media card.
3. Confirm target sites.
4. Search sites by song and album keywords.
5. Filter resources by artist.
6. Submit the chosen torrent to the downloader.
7. Poll the downloader until completion.
8. Refresh the configured media server.
9. Send event-specific notifications.

Phase one explicitly does not scrape or write local audio tags, move files, copy files, or create hard links after download completion.

## Scope

### In Scope

- Metadata pre-search through a Metadata Adapter such as MusicBrainz.
- Media information cards for candidate tracks and releases.
- User-confirmed site selection before PT/BT search.
- Dual keyword site search using song title and album title.
- Artist-based resource filtering.
- Database-backed runtime configuration.
- Persistent downloader, media server, notifier, system setting, and download task storage.
- Polling-based downloader completion monitoring.
- Navidrome media library refresh after download completion.
- Event-scoped notification delivery for download started and library refreshed events.

### Out of Scope

- Local audio metadata scraping and ID3/Vorbis writing.
- Physical file move, copy, or hardlink import.
- qBittorrent webhook mode implementation.
- Automatic relaxed search after artist filtering returns no results.
- Feishu notifier delivery implementation.

## Configuration Persistence

All runtime business configuration is stored in the database. The JSON runtime configuration store and `config/runtime.json` are removed from the active configuration path.

Environment variables remain only for startup-level values that are needed before database-backed configuration can be read:

- Database URL.
- Initial administrator credentials.
- Session secret.
- Log level.
- Static frontend directory.

## Database Model

### `downloaders`

Stores configured downloader instances.

Fields:

- `id`
- `name`
- `type`
- `base_url`
- `username`
- `password`
- `download_path`
- `listen_mode`
- `is_default`
- `enabled`
- `created_at`
- `updated_at`

`listen_mode` supports `polling` and `qb_callback`. Phase one implements only `polling`; `qb_callback` is saved as a reserved option.

### `media_servers`

Stores configured music media library services.

Fields:

- `id`
- `name`
- `type`
- `base_url`
- `api_key` or token
- `username`
- `password`
- `is_default`
- `enabled`
- `created_at`
- `updated_at`

Phase one implements Navidrome refresh behavior.

### `notifier_channels`

Stores configured notification channels.

Fields:

- `id`
- `name`
- `type`
- `bot_token`
- `webhook_url`
- `chat_ids`
- `use_proxy`
- `enable_download_notify`
- `enable_library_notify`
- `enabled`
- `created_at`
- `updated_at`

Notification event subscriptions are stored as boolean fields because the phase one event set is finite and small.

### `system_settings`

Stores global runtime settings. It can use a key/value shape with JSON values because these settings are not repeated business entities.

Initial setting:

- Proxy configuration: host, port, username, password.

### `indexer_sites`

Site configuration remains database-backed. The Alembic migration chain should explicitly create the `indexer_sites` table so the schema is not dependent on `Base.metadata.create_all()`.

### `torrent_records`

The existing `torrent_records` table is used as the download task table and extended instead of introducing a duplicate `download_tasks` table.

Additional or normalized fields should cover:

- `status`
- `torrent_hash`
- `name`
- `source`
- `download_url`
- `progress`
- `save_path`
- `downloader_id`
- `media_metadata`
- `resource_payload`
- `selected_site_ids`
- `submitted_at`
- `download_started_at`
- `completed_at`
- `library_refreshed_at`
- `last_error`
- `payload`
- `created_at`
- `updated_at`

## Search Workflow

### Metadata Pre-search

When the user searches, the frontend first calls a new metadata search API, for example:

`GET /api/metadata/search?query=...`

The backend queries Metadata Adapter providers such as MusicBrainz and returns candidate media cards. Each card represents a concrete recording or recording/release combination.

Card fields:

- Song title.
- Artist.
- Album.
- Release date.
- Cover URL.
- Metadata source.
- External ID.

Same-name songs are split into separate cards when artist or album differs.

### No Metadata Result Fallback

If metadata pre-search returns no candidates, the frontend prompts:

Prompt text: &#26410;&#25214;&#21040;&#23186;&#20307;&#20449;&#24687;&#65292;&#26159;&#21542;&#30452;&#25509;&#20351;&#29992;&#31449;&#28857;&#25628;&#32034;&#65311;

If the user confirms, the frontend calls the existing direct site search flow. If the user cancels, the search ends.

### Site Search Confirmation

When the user selects a media card, the frontend opens a search confirmation dialog. The dialog lists enabled PT/BT sites as checkboxes, defaulting to selected.

Clicking the execute-search action calls a metadata-driven site search API, for example:

`POST /api/search/by-metadata`

The request includes:

- Selected media card.
- Selected site IDs.
- Result limit.

### Site Search and Filter

The backend searches only the selected sites.

Search keywords:

- Song title.
- Album title, when present.

Results from both searches are merged and deduplicated. The backend then filters resource text by the selected media card artist. Resource text may include title, subtitle, details summary, and any parser-provided text available in the current indexer result.

Filtered results are ranked by seeders and returned as resource cards. The response includes raw and filtered counts so the frontend can distinguish no site results from all results being filtered out.

If filtering removes all results, phase one returns an empty result set and the frontend displays that the artist filter found no matching resources. It does not automatically relax the filter.

## Download Workflow

The user downloads from a resource card. The frontend calls:

`POST /api/downloads`

The request includes:

- Resource snapshot.
- Selected media metadata snapshot.
- Download category.

The backend creates or updates a `torrent_records` task and submits the resource to the default enabled downloader.

On successful downloader submission:

- The task moves from `queued` to `submitted`.
- The backend tries to resolve and store the downloader task hash.
- A download-started notification is sent to enabled notifier channels with `enable_download_notify = true`.

qBittorrent does not directly return a torrent hash from the add API. Phase one resolves the hash by querying the downloader after submission and matching the newly added task by URL, title, or other stable resource attributes available from the downloader. If immediate matching fails, the task remains `submitted`, records a warning, and later polling attempts to backfill the hash.

## Download Task State Machine

States:

- `queued`: task created but not submitted.
- `submitted`: downloader add API succeeded.
- `downloading`: polling sees the task and it is not complete.
- `completed`: polling sees the task as complete.
- `refreshing_library`: media server refresh is in progress.
- `library_refreshed`: media server refresh succeeded and the workflow is complete.
- `failed`: an unrecoverable submit, polling, or refresh error occurred.

State changes are persisted to `torrent_records`.

## Background Polling and Refresh

The background polling worker starts only for the default enabled downloader when `listen_mode = polling`.

The worker regularly loads unfinished tasks in these states:

- `submitted`
- `downloading`
- `completed`
- `refreshing_library`

For submitted or downloading tasks, it calls the downloader status API, updates progress and save path, and advances to `completed` once the downloader reports completion.

For completed tasks, it calls the default enabled media server refresh API.

For Navidrome:

- Prefer `/rest/ping.view` for connection tests.
- Use `/rest/startScan.view` for refresh.

If Navidrome refresh returns HTTP 200 without API error, the task advances to `library_refreshed` and a library-refreshed notification is sent to enabled notifier channels with `enable_library_notify = true`.

If refresh fails, phase one marks the task `failed` and stores `last_error`. Retry policy can be added later.

## Relationship to Existing Processing Code

The new phase one download completion path does not call `MediaProcessor`.

Existing file-processing components can remain in the repository for later phases:

- Audio file discovery.
- Hardlink import.
- Mutagen tag writing.
- Processed media repository writes.

The qBittorrent webhook endpoint can remain, but when it receives a completion event in phase one it should only advance the download task and trigger media server refresh. It must not invoke local file processing.

`/api/media` and the existing media records page may remain, but this phase does not add new media records.

## System Settings UI

The Settings page becomes a unified system settings page with module cards.

### Downloader Card

Controls:

- Downloader list.
- Add/edit/test actions.
- Type.
- Name.
- Base URL.
- Username.
- Password.
- Download path.
- Listen mode: polling or qB callback.
- Default flag.
- Enabled flag.

The qB callback option is labeled as reserved for phase one.

### Media Server Card

Controls:

- Media server list.
- Add/edit/test actions.
- Type: Navidrome for phase one.
- Name.
- Base URL.
- API token or username/password.
- Default flag.
- Enabled flag.

### Notifier Card

Controls:

- Notifier channel list.
- Add/edit/test actions.
- Type: Telegram for phase one.
- Name.
- Bot token or webhook URL.
- Chat IDs.
- Use system proxy.
- Enabled flag.
- Download notification toggle.
- Library notification toggle.

Feishu can be reserved as a future type but is not implemented in phase one.

### Network Settings Card

Controls:

- Proxy host.
- Proxy port.
- Proxy username.
- Proxy password.

Editing password fields with an empty value keeps the existing secret.

## API Changes

Configuration APIs read and write database tables:

- `GET/POST/PUT /api/settings/downloaders`
- `GET/POST/PUT /api/settings/media-servers`
- `GET/POST/PUT /api/settings/notifiers`
- `GET/PUT /api/settings/system`

Search APIs:

- `GET /api/metadata/search`
- `POST /api/search/by-metadata`
- Existing `/api/search/stream` remains as the direct site-search fallback.

Download APIs:

- `POST /api/downloads` creates and submits a persistent task.
- `GET /api/downloads` returns database task state rather than directly proxying the downloader list.

Webhook API:

- qB webhook remains reserved.
- If used, it advances task state and triggers refresh only.

## Testing

Backend tests:

- Configuration repositories for downloaders, media servers, notifiers, and system settings.
- Alembic schema coverage for newly added tables and `indexer_sites`.
- Metadata candidate search mapping.
- No-result metadata fallback API behavior.
- Metadata-driven site search using selected site IDs.
- Artist filter behavior and raw/filtered counts.
- Download task creation and state transition.
- Polling worker transition from submitted to downloading to completed.
- Navidrome refresh transition to library refreshed.
- Notification routing by `enable_download_notify` and `enable_library_notify`.

Frontend verification:

- Build check.
- Search no-metadata fallback confirm/cancel behavior.
- Metadata card selection and site confirmation dialog.
- Resource cards and download submission.
- Unified settings page cards.
- Browser verification against the local dev server after implementation.

## Open Decisions

No open product decisions remain for phase one. Implementation may choose exact API response field names and repository method names as long as the behavior above is preserved.
