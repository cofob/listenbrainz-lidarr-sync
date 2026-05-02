from __future__ import annotations

import pytest

from listenbrainz_lidarr_sync.config import (
    ENV_PREFIX,
    MonitorType,
    NewItemMonitorType,
    extract_mbid,
    load_config_from_env,
)

TELEGRAM_TEST_TOKEN = "bot" + "-token"


def test_load_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}LIDARR_URL", "http://lidarr:8686/")
    monkeypatch.setenv(f"{ENV_PREFIX}LIDARR_API_KEY", "secret")
    monkeypatch.setenv(f"{ENV_PREFIX}LISTENBRAINZ_USER", "alice")

    config = load_config_from_env()

    assert config.lidarr_url == "http://lidarr:8686"
    assert config.listenbrainz_user == "alice"
    assert config.interval_seconds == 86_400
    assert config.artist_monitored is True
    assert config.artist_add_monitor is MonitorType.LATEST
    assert config.artist_monitor_new_items is NewItemMonitorType.NEW
    assert config.search_for_missing_albums is False
    assert config.search_wanted_albums is False
    assert config.telegram_bot_token is None
    assert config.telegram_chat_id is None
    assert config.telegram_message_thread_id is None
    assert config.telegram_report_success is True
    assert config.telegram_report_failure is True


def test_load_config_parses_playlist_ids_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    playlist_mbid = "6f9619ff-8b86-d011-b42d-00cf4fc964ff"
    monkeypatch.setenv(f"{ENV_PREFIX}LIDARR_URL", "http://lidarr:8686")
    monkeypatch.setenv(f"{ENV_PREFIX}LIDARR_API_KEY", "secret")
    monkeypatch.setenv(f"{ENV_PREFIX}LISTENBRAINZ_USER", "alice")
    monkeypatch.setenv(f"{ENV_PREFIX}PLAYLIST_MBIDS", f"https://listenbrainz.org/playlist/{playlist_mbid}")
    monkeypatch.setenv(f"{ENV_PREFIX}ARTIST_ADD_MONITOR", "all")
    monkeypatch.setenv(f"{ENV_PREFIX}ARTIST_MONITOR_NEW_ITEMS", "all")
    monkeypatch.setenv(f"{ENV_PREFIX}SEARCH_FOR_MISSING_ALBUMS", "yes")
    monkeypatch.setenv(f"{ENV_PREFIX}SEARCH_WANTED_ALBUMS", "yes")

    config = load_config_from_env()

    assert config.playlist_mbids == (playlist_mbid,)
    assert config.artist_add_monitor is MonitorType.ALL
    assert config.artist_monitor_new_items is NewItemMonitorType.ALL
    assert config.search_for_missing_albums is True
    assert config.search_wanted_albums is True


def test_load_config_parses_telegram_reporting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}LIDARR_URL", "http://lidarr:8686")
    monkeypatch.setenv(f"{ENV_PREFIX}LIDARR_API_KEY", "secret")
    monkeypatch.setenv(f"{ENV_PREFIX}LISTENBRAINZ_USER", "alice")
    monkeypatch.setenv(f"{ENV_PREFIX}TELEGRAM_BOT_TOKEN", TELEGRAM_TEST_TOKEN)
    monkeypatch.setenv(f"{ENV_PREFIX}TELEGRAM_CHAT_ID", "-100123456789")
    monkeypatch.setenv(f"{ENV_PREFIX}TELEGRAM_MESSAGE_THREAD_ID", "42")
    monkeypatch.setenv(f"{ENV_PREFIX}TELEGRAM_REPORT_SUCCESS", "false")
    monkeypatch.setenv(f"{ENV_PREFIX}TELEGRAM_REPORT_FAILURE", "true")

    config = load_config_from_env()

    assert config.telegram_bot_token == TELEGRAM_TEST_TOKEN
    assert config.telegram_chat_id == "-100123456789"
    assert config.telegram_message_thread_id == 42
    assert config.telegram_report_success is False
    assert config.telegram_report_failure is True


def test_load_config_requires_complete_telegram_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}LIDARR_URL", "http://lidarr:8686")
    monkeypatch.setenv(f"{ENV_PREFIX}LIDARR_API_KEY", "secret")
    monkeypatch.setenv(f"{ENV_PREFIX}LISTENBRAINZ_USER", "alice")
    monkeypatch.setenv(f"{ENV_PREFIX}TELEGRAM_BOT_TOKEN", TELEGRAM_TEST_TOKEN)

    with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
        load_config_from_env()


def test_extract_mbid_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="Expected a MusicBrainz ID"):
        extract_mbid("not-a-mbid")
