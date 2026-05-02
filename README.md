# listenbrainz-lidarr-sync

Import ListenBrainz recommendation playlists into Lidarr.

The sync reads ListenBrainz playlists created for a user, resolves playlist tracks through MusicBrainz to release
groups and artists, then marks the matching Lidarr albums as wanted. Missing artists are added to Lidarr first.

## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/)
- Lidarr API access

## Installation

```bash
uv sync
```

## Configuration

Required environment variables:

```bash
export LISTENBRAINZ_LIDARR_SYNC_LIDARR_URL="http://lidarr:8686"
export LISTENBRAINZ_LIDARR_SYNC_LIDARR_API_KEY="your_lidarr_api_key"
export LISTENBRAINZ_LIDARR_SYNC_LISTENBRAINZ_USER="listenbrainz_username"
```

Optional playlist selection:

```bash
export LISTENBRAINZ_LIDARR_SYNC_LISTENBRAINZ_TOKEN="optional_listenbrainz_token"
export LISTENBRAINZ_LIDARR_SYNC_PLAYLIST_MBIDS="playlist-mbid-or-url,another-mbid"
export LISTENBRAINZ_LIDARR_SYNC_PLAYLIST_TITLE_INCLUDE="weekly,recommendation"
export LISTENBRAINZ_LIDARR_SYNC_PLAYLIST_TITLE_EXCLUDE="archive"
```

`LISTENBRAINZ_LIDARR_SYNC_PLAYLIST_TITLE_INCLUDE` selects only the first matching playlist returned by ListenBrainz,
which is treated as the latest recommendation playlist. Use `LISTENBRAINZ_LIDARR_SYNC_PLAYLIST_MBIDS` for additional
explicit playlists.

Optional Lidarr defaults:

```bash
export LISTENBRAINZ_LIDARR_SYNC_LIDARR_ROOT_FOLDER_PATH="/music"
export LISTENBRAINZ_LIDARR_SYNC_LIDARR_QUALITY_PROFILE_ID="1"
export LISTENBRAINZ_LIDARR_SYNC_LIDARR_METADATA_PROFILE_ID="1"
export LISTENBRAINZ_LIDARR_SYNC_ARTIST_MONITORED="true"
export LISTENBRAINZ_LIDARR_SYNC_ARTIST_ADD_MONITOR="latest"
export LISTENBRAINZ_LIDARR_SYNC_ARTIST_MONITOR_NEW_ITEMS="new"
export LISTENBRAINZ_LIDARR_SYNC_SEARCH_FOR_MISSING_ALBUMS="false"
export LISTENBRAINZ_LIDARR_SYNC_INTERVAL_SECONDS="86400"
```

If root folder path or profile IDs are omitted, the sync uses the selected root folder defaults. When Lidarr has
multiple root folders, `LISTENBRAINZ_LIDARR_SYNC_LIDARR_ROOT_FOLDER_PATH` is required.

Optional Telegram result reporting:

```bash
export LISTENBRAINZ_LIDARR_SYNC_TELEGRAM_BOT_TOKEN="123456:bot_token"
export LISTENBRAINZ_LIDARR_SYNC_TELEGRAM_CHAT_ID="-1001234567890"
export LISTENBRAINZ_LIDARR_SYNC_TELEGRAM_MESSAGE_THREAD_ID="42"
export LISTENBRAINZ_LIDARR_SYNC_TELEGRAM_REPORT_SUCCESS="true"
export LISTENBRAINZ_LIDARR_SYNC_TELEGRAM_REPORT_FAILURE="true"
```

`LISTENBRAINZ_LIDARR_SYNC_TELEGRAM_MESSAGE_THREAD_ID` is only needed for forum topics. Telegram reporting is disabled
unless both bot token and chat id are set.

## Usage

Run once:

```bash
uv run listenbrainz-lidarr-sync
```

Run continuously:

```bash
uv run listenbrainz-lidarr-sync --watch --interval-seconds 86400
```

Preview Lidarr writes:

```bash
uv run listenbrainz-lidarr-sync --dry-run
```

## Behavior

- Playlist metadata is fetched from ListenBrainz `createdfor` playlists.
- Playlist tracks are resolved from MusicBrainz release MBIDs first, then recording MBIDs as a fallback.
- Lidarr albums are matched by MusicBrainz release-group MBID.
- Albums already monitored or already downloaded are skipped.
- Existing artist settings are not changed.
- New artists are monitored by default and added with Lidarr's `latest` monitor option.

The Lidarr OpenAPI reference used while implementing the client is checked in at `schemas/lidarr.openapi.json`.

## Development

```bash
uv sync --group dev
uv run ruff check .
uv run mypy listenbrainz_lidarr_sync tests
uv run pytest
```
