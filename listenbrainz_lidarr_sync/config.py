from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import StrEnum

ENV_PREFIX = "LISTENBRAINZ_LIDARR_SYNC_"
DEFAULT_INTERVAL_SECONDS = 86_400
MBID_PATTERN = re.compile(r"(?P<mbid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")


class MonitorType(StrEnum):
    ALL = "all"
    FUTURE = "future"
    MISSING = "missing"
    EXISTING = "existing"
    LATEST = "latest"
    FIRST = "first"
    NONE = "none"
    UNKNOWN = "unknown"


class NewItemMonitorType(StrEnum):
    ALL = "all"
    NONE = "none"
    NEW = "new"


@dataclass(frozen=True, slots=True)
class Config:
    lidarr_url: str
    lidarr_api_key: str
    listenbrainz_user: str
    listenbrainz_token: str | None
    playlist_mbids: tuple[str, ...]
    playlist_title_include: tuple[str, ...]
    playlist_title_exclude: tuple[str, ...]
    interval_seconds: int
    lidarr_root_folder_path: str | None
    lidarr_quality_profile_id: int | None
    lidarr_metadata_profile_id: int | None
    artist_monitored: bool
    artist_add_monitor: MonitorType
    artist_monitor_new_items: NewItemMonitorType
    search_for_missing_albums: bool
    search_wanted_albums: bool
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    telegram_message_thread_id: int | None
    telegram_report_success: bool
    telegram_report_failure: bool


def env_name(name: str) -> str:
    return f"{ENV_PREFIX}{name}"


def get_str_env(name: str, *, default: str | None = None) -> str:
    value = os.getenv(env_name(name))
    if value is None:
        if default is None:
            raise ValueError(f"Missing required environment variable: {env_name(name)}")
        return default
    stripped = value.strip()
    if not stripped and default is None:
        raise ValueError(f"Environment variable {env_name(name)} must not be empty.")
    return stripped or (default if default is not None else stripped)


def get_optional_str_env(name: str) -> str | None:
    value = os.getenv(env_name(name))
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def get_int_env(name: str, *, default: int | None = None) -> int:
    value = os.getenv(env_name(name))
    if value is None:
        if default is None:
            raise ValueError(f"Missing required environment variable: {env_name(name)}")
        return default
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ValueError(f"Environment variable {env_name(name)} must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"Environment variable {env_name(name)} must be greater than zero.")
    return parsed


def get_optional_int_env(name: str) -> int | None:
    value = os.getenv(env_name(name))
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ValueError(f"Environment variable {env_name(name)} must be an integer.") from exc
    if parsed <= 0:
        raise ValueError(f"Environment variable {env_name(name)} must be greater than zero.")
    return parsed


def get_bool_env(name: str, *, default: bool) -> bool:
    value = os.getenv(env_name(name))
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Environment variable {env_name(name)} must be a boolean.")


def get_csv_env(name: str) -> tuple[str, ...]:
    value = os.getenv(env_name(name))
    if value is None:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def get_mbid_csv_env(name: str) -> tuple[str, ...]:
    return tuple(extract_mbid(part) for part in get_csv_env(name))


def extract_mbid(value: str) -> str:
    match = MBID_PATTERN.search(value)
    if match is None:
        raise ValueError(f"Expected a MusicBrainz ID or URL, got: {value}")
    return match.group("mbid").lower()


def get_monitor_type_env(name: str, *, default: MonitorType) -> MonitorType:
    value = get_optional_str_env(name)
    if value is None:
        return default
    try:
        return MonitorType(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in MonitorType)
        raise ValueError(f"Environment variable {env_name(name)} must be one of: {allowed}.") from exc


def get_new_item_monitor_type_env(name: str, *, default: NewItemMonitorType) -> NewItemMonitorType:
    value = get_optional_str_env(name)
    if value is None:
        return default
    try:
        return NewItemMonitorType(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in NewItemMonitorType)
        raise ValueError(f"Environment variable {env_name(name)} must be one of: {allowed}.") from exc


def load_config_from_env() -> Config:
    config = Config(
        lidarr_url=get_str_env("LIDARR_URL").rstrip("/"),
        lidarr_api_key=get_str_env("LIDARR_API_KEY"),
        listenbrainz_user=get_str_env("LISTENBRAINZ_USER"),
        listenbrainz_token=get_optional_str_env("LISTENBRAINZ_TOKEN"),
        playlist_mbids=get_mbid_csv_env("PLAYLIST_MBIDS"),
        playlist_title_include=get_csv_env("PLAYLIST_TITLE_INCLUDE"),
        playlist_title_exclude=get_csv_env("PLAYLIST_TITLE_EXCLUDE"),
        interval_seconds=get_int_env("INTERVAL_SECONDS", default=DEFAULT_INTERVAL_SECONDS),
        lidarr_root_folder_path=get_optional_str_env("LIDARR_ROOT_FOLDER_PATH"),
        lidarr_quality_profile_id=get_optional_int_env("LIDARR_QUALITY_PROFILE_ID"),
        lidarr_metadata_profile_id=get_optional_int_env("LIDARR_METADATA_PROFILE_ID"),
        artist_monitored=get_bool_env("ARTIST_MONITORED", default=True),
        artist_add_monitor=get_monitor_type_env("ARTIST_ADD_MONITOR", default=MonitorType.LATEST),
        artist_monitor_new_items=get_new_item_monitor_type_env(
            "ARTIST_MONITOR_NEW_ITEMS",
            default=NewItemMonitorType.NEW,
        ),
        search_for_missing_albums=get_bool_env("SEARCH_FOR_MISSING_ALBUMS", default=False),
        search_wanted_albums=get_bool_env("SEARCH_WANTED_ALBUMS", default=False),
        telegram_bot_token=get_optional_str_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=get_optional_str_env("TELEGRAM_CHAT_ID"),
        telegram_message_thread_id=get_optional_int_env("TELEGRAM_MESSAGE_THREAD_ID"),
        telegram_report_success=get_bool_env("TELEGRAM_REPORT_SUCCESS", default=True),
        telegram_report_failure=get_bool_env("TELEGRAM_REPORT_FAILURE", default=True),
    )
    validate_telegram_config(config)
    return config


def validate_telegram_config(config: Config) -> None:
    if config.telegram_bot_token is None and config.telegram_chat_id is None:
        return
    if config.telegram_bot_token is None:
        raise ValueError(f"Set {env_name('TELEGRAM_BOT_TOKEN')} when Telegram reporting is configured.")
    if config.telegram_chat_id is None:
        raise ValueError(f"Set {env_name('TELEGRAM_CHAT_ID')} when Telegram reporting is configured.")
