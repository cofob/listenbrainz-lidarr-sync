from __future__ import annotations

import json

import httpx

from listenbrainz_lidarr_sync.models import SyncStats
from listenbrainz_lidarr_sync.telegram import TelegramReporter, format_failure_message, format_success_message


def test_telegram_reporter_sends_message_to_thread() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    reporter = TelegramReporter(
        httpx.Client(base_url="https://api.telegram.org", transport=httpx.MockTransport(handler)),
        bot_token="token",
        chat_id="-100123456789",
        message_thread_id=42,
    )

    reporter.send_success(
        SyncStats(playlists_seen=1, tracks_seen=2, albums_marked_wanted=3, album_searches_triggered=1),
        dry_run=True,
    )

    assert len(requests) == 1
    assert requests[0].url.path == "/bottoken/sendMessage"
    payload = json.loads(requests[0].content)
    assert payload["chat_id"] == "-100123456789"
    assert payload["message_thread_id"] == 42
    assert "dry run" in payload["text"]
    assert "Albums marked wanted: 3" in payload["text"]
    assert "Album searches triggered: 1" in payload["text"]


def test_format_failure_message_truncates_long_error() -> None:
    message = format_failure_message(RuntimeError("x" * 1200), dry_run=False)

    assert message.startswith("ListenBrainz Lidarr sync failed (live).")
    assert len(message) < 1100
    assert message.endswith("...")


def test_format_success_message_includes_stats() -> None:
    message = format_success_message(
        SyncStats(
            playlists_seen=1,
            tracks_seen=2,
            albums_resolved=3,
            artists_added=4,
            albums_marked_wanted=5,
            album_searches_triggered=6,
            albums_skipped_wanted=6,
            albums_skipped_downloaded=7,
            albums_skipped_missing_in_lidarr=8,
        ),
        dry_run=False,
    )

    assert "ListenBrainz Lidarr sync finished (live)." in message
    assert "Playlists: 1" in message
    assert "Album searches triggered: 6" in message
    assert "Skipped missing in Lidarr: 8" in message
