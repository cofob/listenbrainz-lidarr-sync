from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

import httpx

from listenbrainz_lidarr_sync.config import Config, MonitorType, NewItemMonitorType
from listenbrainz_lidarr_sync.json_types import JsonValue
from listenbrainz_lidarr_sync.lidarr import LidarrClient
from listenbrainz_lidarr_sync.listenbrainz import ListenBrainzClient
from listenbrainz_lidarr_sync.musicbrainz import MusicBrainzResolver
from listenbrainz_lidarr_sync.sync import SyncService

PLAYLIST_MBID = "6f9619ff-8b86-d011-b42d-00cf4fc964ff"
RELEASE_MBID = "189002e7-3285-4e2e-92a3-7f6c30d407a2"
RELEASE_GROUP_MBID = "e66b3779-0944-4fd6-9f2f-45f6285532c6"
ARTIST_MBID = "0383dadf-2a4e-4d10-a46a-e9e041da8eb3"


def test_sync_adds_missing_artist_and_marks_album_wanted() -> None:
    lidarr_state = {"artist_added": False, "album_monitored": False}

    def listenbrainz_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/playlists/createdfor"):
            return httpx.Response(
                200,
                json={
                    "playlist": {
                        "playlists": [
                            {
                                "playlist": {
                                    "title": "Weekly Exploration",
                                    "identifier": [f"https://listenbrainz.org/playlist/{PLAYLIST_MBID}"],
                                }
                            }
                        ]
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "playlist": {
                    "track": [
                        {
                            "title": "A Song",
                            "identifier": ["https://musicbrainz.org/recording/b1a9c0e9-d987-4042-ae91-78d6a3267d69"],
                            "release_identifier": [f"https://musicbrainz.org/release/{RELEASE_MBID}"],
                            "artist_identifiers": [f"https://musicbrainz.org/artist/{ARTIST_MBID}"],
                        }
                    ]
                }
            },
        )

    def lidarr_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/rootfolder":
            return httpx.Response(
                200,
                json=[
                    {
                        "path": "/music",
                        "defaultQualityProfileId": 1,
                        "defaultMetadataProfileId": 2,
                    }
                ],
            )
        if request.url.path == "/api/v1/artist" and request.method == "GET":
            if lidarr_state["artist_added"]:
                return httpx.Response(200, json=[{"id": 10, "foreignArtistId": ARTIST_MBID, "artistName": "Queen"}])
            return httpx.Response(200, json=[])
        if request.url.path == "/api/v1/artist/lookup":
            return httpx.Response(200, json=[{"id": 0, "foreignArtistId": ARTIST_MBID, "artistName": "Queen"}])
        if request.url.path == "/api/v1/artist" and request.method == "POST":
            payload = json.loads(request.content)
            assert payload["rootFolderPath"] == "/music"
            assert payload["qualityProfileId"] == 1
            assert payload["metadataProfileId"] == 2
            assert payload["addOptions"]["monitor"] == "latest"
            lidarr_state["artist_added"] = True
            return httpx.Response(200, json={"id": 10, "foreignArtistId": ARTIST_MBID, "artistName": "Queen"})
        if request.url.path == "/api/v1/album" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 20,
                        "foreignAlbumId": RELEASE_GROUP_MBID,
                        "title": "Album",
                        "monitored": False,
                        "statistics": {"trackFileCount": 0},
                    }
                ],
            )
        if request.url.path == "/api/v1/album/monitor" and request.method == "PUT":
            payload = json.loads(request.content)
            assert payload == {"albumIds": [20], "monitored": True}
            lidarr_state["album_monitored"] = True
            return httpx.Response(202, json={})
        return httpx.Response(404, json={"path": request.url.path})

    service = SyncService(
        config=_config(),
        listenbrainz=ListenBrainzClient(
            httpx.Client(base_url="https://api.listenbrainz.org", transport=httpx.MockTransport(listenbrainz_handler)),
            user="alice",
        ),
        musicbrainz=MusicBrainzResolver(_FakeMusicBrainzLookup()),
        lidarr=LidarrClient(
            httpx.Client(base_url="http://lidarr:8686", transport=httpx.MockTransport(lidarr_handler)),
            config=_config(),
        ),
    )

    stats = service.run_once()

    assert lidarr_state == {"artist_added": True, "album_monitored": True}
    assert stats.playlists_seen == 1
    assert stats.tracks_seen == 1
    assert stats.albums_resolved == 1
    assert stats.artists_added == 1
    assert stats.albums_marked_wanted == 1
    assert stats.album_searches_triggered == 0


def test_sync_uses_lidarr_album_title_fast_path_without_musicbrainz_lookup() -> None:
    lidarr_state = {"album_requests": 0, "album_monitored": False}

    def listenbrainz_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/playlists/createdfor"):
            return httpx.Response(
                200,
                json={
                    "playlist": {
                        "playlists": [
                            {
                                "playlist": {
                                    "title": "Weekly Exploration",
                                    "identifier": [f"https://listenbrainz.org/playlist/{PLAYLIST_MBID}"],
                                }
                            }
                        ]
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "playlist": {
                    "track": [
                        {
                            "album": "Album",
                            "title": "A Song",
                            "identifier": ["https://musicbrainz.org/recording/b1a9c0e9-d987-4042-ae91-78d6a3267d69"],
                            "artist_identifiers": [f"https://musicbrainz.org/artist/{ARTIST_MBID}"],
                        }
                    ]
                }
            },
        )

    def lidarr_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/rootfolder":
            return httpx.Response(
                200,
                json=[{"path": "/music", "defaultQualityProfileId": 1, "defaultMetadataProfileId": 2}],
            )
        if request.url.path == "/api/v1/artist" and request.method == "GET":
            return httpx.Response(200, json=[{"id": 10, "foreignArtistId": ARTIST_MBID, "artistName": "Queen"}])
        if request.url.path == "/api/v1/album" and request.method == "GET":
            lidarr_state["album_requests"] += 1
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 20,
                        "foreignAlbumId": RELEASE_GROUP_MBID,
                        "title": "Album",
                        "monitored": False,
                        "statistics": {"trackFileCount": 0},
                    }
                ],
            )
        if request.url.path == "/api/v1/album/monitor" and request.method == "PUT":
            lidarr_state["album_monitored"] = True
            return httpx.Response(202, json={})
        return httpx.Response(404, json={"path": request.url.path})

    service = SyncService(
        config=_config(),
        listenbrainz=ListenBrainzClient(
            httpx.Client(base_url="https://api.listenbrainz.org", transport=httpx.MockTransport(listenbrainz_handler)),
            user="alice",
        ),
        musicbrainz=MusicBrainzResolver(_UnusedMusicBrainzLookup()),
        lidarr=LidarrClient(
            httpx.Client(base_url="http://lidarr:8686", transport=httpx.MockTransport(lidarr_handler)),
            config=_config(),
        ),
    )

    stats = service.run_once()

    assert lidarr_state == {"album_requests": 1, "album_monitored": True}
    assert stats.albums_resolved == 1
    assert stats.albums_marked_wanted == 1


def test_sync_triggers_album_search_when_configured() -> None:
    lidarr_state = {"album_monitored": False, "album_searched": False}

    def listenbrainz_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/playlists/createdfor"):
            return httpx.Response(
                200,
                json={
                    "playlist": {
                        "playlists": [
                            {
                                "playlist": {
                                    "title": "Weekly Exploration",
                                    "identifier": [f"https://listenbrainz.org/playlist/{PLAYLIST_MBID}"],
                                }
                            }
                        ]
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "playlist": {
                    "track": [
                        {
                            "title": "A Song",
                            "identifier": ["https://musicbrainz.org/recording/b1a9c0e9-d987-4042-ae91-78d6a3267d69"],
                            "release_identifier": [f"https://musicbrainz.org/release/{RELEASE_MBID}"],
                            "artist_identifiers": [f"https://musicbrainz.org/artist/{ARTIST_MBID}"],
                        }
                    ]
                }
            },
        )

    def lidarr_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/rootfolder":
            return httpx.Response(
                200,
                json=[{"path": "/music", "defaultQualityProfileId": 1, "defaultMetadataProfileId": 2}],
            )
        if request.url.path == "/api/v1/artist" and request.method == "GET":
            return httpx.Response(200, json=[{"id": 10, "foreignArtistId": ARTIST_MBID, "artistName": "Queen"}])
        if request.url.path == "/api/v1/album" and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 20,
                        "foreignAlbumId": RELEASE_GROUP_MBID,
                        "title": "Album",
                        "monitored": False,
                        "statistics": {"trackFileCount": 0},
                    }
                ],
            )
        if request.url.path == "/api/v1/album/monitor" and request.method == "PUT":
            lidarr_state["album_monitored"] = True
            return httpx.Response(202, json={})
        if request.url.path == "/api/v1/command" and request.method == "POST":
            payload = json.loads(request.content)
            assert payload == {"name": "AlbumSearch", "albumIds": [20]}
            lidarr_state["album_searched"] = True
            return httpx.Response(200, json={"id": 30, "name": "AlbumSearch"})
        return httpx.Response(404, json={"path": request.url.path})

    service = SyncService(
        config=_config(search_wanted_albums=True),
        listenbrainz=ListenBrainzClient(
            httpx.Client(base_url="https://api.listenbrainz.org", transport=httpx.MockTransport(listenbrainz_handler)),
            user="alice",
        ),
        musicbrainz=MusicBrainzResolver(_FakeMusicBrainzLookup()),
        lidarr=LidarrClient(
            httpx.Client(base_url="http://lidarr:8686", transport=httpx.MockTransport(lidarr_handler)),
            config=_config(search_wanted_albums=True),
        ),
    )

    stats = service.run_once()

    assert lidarr_state == {"album_monitored": True, "album_searched": True}
    assert stats.albums_marked_wanted == 1
    assert stats.album_searches_triggered == 1


class _FakeMusicBrainzLookup:
    def get_release_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        assert mbid == RELEASE_MBID
        assert "release-groups" in includes
        return {
            "release": {
                "id": RELEASE_MBID,
                "title": "Release",
                "release-group": {"id": RELEASE_GROUP_MBID, "title": "Album"},
                "artist-credit": [{"artist": {"id": ARTIST_MBID}}],
            }
        }

    def get_recording_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        raise AssertionError(f"recording fallback should not be used for {mbid} with {includes}")


class _UnusedMusicBrainzLookup:
    def get_release_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        raise AssertionError(f"MusicBrainz release lookup should not be used for {mbid} with {includes}")

    def get_recording_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        raise AssertionError(f"MusicBrainz recording lookup should not be used for {mbid} with {includes}")


def _config(*, search_wanted_albums: bool = False) -> Config:
    return Config(
        lidarr_url="http://lidarr:8686",
        lidarr_api_key="secret",
        listenbrainz_user="alice",
        listenbrainz_token=None,
        playlist_mbids=(),
        playlist_title_include=(),
        playlist_title_exclude=(),
        interval_seconds=86_400,
        lidarr_root_folder_path=None,
        lidarr_quality_profile_id=None,
        lidarr_metadata_profile_id=None,
        artist_monitored=True,
        artist_add_monitor=MonitorType.LATEST,
        artist_monitor_new_items=NewItemMonitorType.NEW,
        search_for_missing_albums=False,
        search_wanted_albums=search_wanted_albums,
        telegram_bot_token=None,
        telegram_chat_id=None,
        telegram_message_thread_id=None,
        telegram_report_success=True,
        telegram_report_failure=True,
    )
