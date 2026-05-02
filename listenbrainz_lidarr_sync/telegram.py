from __future__ import annotations

import httpx

from listenbrainz_lidarr_sync.config import Config
from listenbrainz_lidarr_sync.models import SyncStats

MAX_ERROR_MESSAGE_LENGTH = 1000


class TelegramReporter:
    def __init__(
        self,
        client: httpx.Client,
        *,
        bot_token: str,
        chat_id: str,
        message_thread_id: int | None,
    ) -> None:
        self._client = client
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._message_thread_id = message_thread_id

    def send_success(self, stats: SyncStats, *, dry_run: bool) -> None:
        self._send_message(format_success_message(stats, dry_run=dry_run))

    def send_failure(self, exc: Exception, *, dry_run: bool) -> None:
        self._send_message(format_failure_message(exc, dry_run=dry_run))

    def _send_message(self, text: str) -> None:
        payload: dict[str, str | int | bool] = {
            "chat_id": self._chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if self._message_thread_id is not None:
            payload["message_thread_id"] = self._message_thread_id

        response = self._client.post(f"/bot{self._bot_token}/sendMessage", json=payload)
        response.raise_for_status()


def build_reporter(config: Config) -> TelegramReporter | None:
    if config.telegram_bot_token is None or config.telegram_chat_id is None:
        return None
    return TelegramReporter(
        create_http_client(),
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        message_thread_id=config.telegram_message_thread_id,
    )


def create_http_client() -> httpx.Client:
    return httpx.Client(base_url="https://api.telegram.org", timeout=30.0)


def format_success_message(stats: SyncStats, *, dry_run: bool) -> str:
    mode = "dry run" if dry_run else "live"
    return (
        f"ListenBrainz Lidarr sync finished ({mode}).\n"
        f"Playlists: {stats.playlists_seen}\n"
        f"Tracks: {stats.tracks_seen}\n"
        f"Resolved albums: {stats.albums_resolved}\n"
        f"Artists added: {stats.artists_added}\n"
        f"Albums marked wanted: {stats.albums_marked_wanted}\n"
        f"Skipped wanted: {stats.albums_skipped_wanted}\n"
        f"Skipped downloaded: {stats.albums_skipped_downloaded}\n"
        f"Skipped missing in Lidarr: {stats.albums_skipped_missing_in_lidarr}"
    )


def format_failure_message(exc: Exception, *, dry_run: bool) -> str:
    mode = "dry run" if dry_run else "live"
    message = str(exc).strip()
    if len(message) > MAX_ERROR_MESSAGE_LENGTH:
        message = f"{message[: MAX_ERROR_MESSAGE_LENGTH - 3]}..."
    return f"ListenBrainz Lidarr sync failed ({mode}).\n{exc.__class__.__name__}: {message}"
