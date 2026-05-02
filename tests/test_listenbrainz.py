from __future__ import annotations

from listenbrainz_lidarr_sync.json_types import JsonMapping
from listenbrainz_lidarr_sync.listenbrainz import filter_playlists, parse_playlist_summaries, parse_playlist_tracks
from listenbrainz_lidarr_sync.models import PlaylistSummary

PLAYLIST_MBID = "6f9619ff-8b86-d011-b42d-00cf4fc964ff"
RECORDING_MBID = "b1a9c0e9-d987-4042-ae91-78d6a3267d69"
RELEASE_MBID = "189002e7-3285-4e2e-92a3-7f6c30d407a2"
ARTIST_MBID = "0383dadf-2a4e-4d10-a46a-e9e041da8eb3"


def test_parse_playlist_summaries_handles_jspf_wrappers() -> None:
    payload: JsonMapping = {
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
    }

    playlists = parse_playlist_summaries(payload)

    assert playlists == [PlaylistSummary(mbid=PLAYLIST_MBID, title="Weekly Exploration")]


def test_parse_playlist_tracks_extracts_musicbrainz_identifiers() -> None:
    payload: JsonMapping = {
        "playlist": {
            "track": [
                {
                    "title": "A Song",
                    "identifier": [f"https://musicbrainz.org/recording/{RECORDING_MBID}"],
                    "release_identifier": [f"https://musicbrainz.org/release/{RELEASE_MBID}"],
                    "artist_identifiers": [f"https://musicbrainz.org/artist/{ARTIST_MBID}"],
                }
            ]
        }
    }

    tracks = parse_playlist_tracks(payload)

    assert len(tracks) == 1
    assert tracks[0].recording_mbid == RECORDING_MBID
    assert tracks[0].release_mbid == RELEASE_MBID
    assert tracks[0].release_group_mbid is None
    assert tracks[0].artist_mbids == (ARTIST_MBID,)
    assert tracks[0].album is None


def test_parse_playlist_tracks_extracts_listenbrainz_extension_metadata() -> None:
    release_group_mbid = "e66b3779-0944-4fd6-9f2f-45f6285532c6"
    payload: JsonMapping = {
        "playlist": {
            "track": [
                {
                    "album": "Demon Days",
                    "title": "Dirty Harry",
                    "identifier": [f"https://musicbrainz.org/recording/{RECORDING_MBID}"],
                    "extension": {
                        "https://musicbrainz.org/doc/jspf#track": {
                            "artist_identifiers": [f"https://musicbrainz.org/artist/{ARTIST_MBID}"],
                            "additional_metadata": {
                                "caa_release_mbid": RELEASE_MBID,
                                "release_group_mbid": release_group_mbid,
                            },
                        }
                    },
                }
            ]
        }
    }

    tracks = parse_playlist_tracks(payload)

    assert len(tracks) == 1
    assert tracks[0].album == "Demon Days"
    assert tracks[0].release_mbid == RELEASE_MBID
    assert tracks[0].release_group_mbid == release_group_mbid
    assert tracks[0].artist_mbids == (ARTIST_MBID,)


def test_filter_playlists_applies_title_and_explicit_rules() -> None:
    selected = filter_playlists(
        [
            PlaylistSummary(mbid=PLAYLIST_MBID, title="Weekly Exploration"),
            PlaylistSummary(mbid="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", title="Archive"),
        ],
        playlist_mbids=("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",),
        title_include=("weekly",),
        title_exclude=("skip",),
    )

    assert selected == [
        PlaylistSummary(mbid=PLAYLIST_MBID, title="Weekly Exploration"),
        PlaylistSummary(mbid="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", title="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
    ]


def test_filter_playlists_matches_slug_style_title_terms() -> None:
    selected = filter_playlists(
        [PlaylistSummary(mbid=PLAYLIST_MBID, title="Weekly Jams for cofobus")],
        playlist_mbids=(),
        title_include=("weekly-jams",),
        title_exclude=(),
    )

    assert selected == [PlaylistSummary(mbid=PLAYLIST_MBID, title="Weekly Jams for cofobus")]


def test_filter_playlists_keeps_only_latest_title_match() -> None:
    latest_mbid = "abdd2153-fb6b-4f20-8980-dbc99d9a010e"
    older_mbid = "4d8d4d21-f0b3-4161-8e06-c5640f8d4a1c"

    selected = filter_playlists(
        [
            PlaylistSummary(mbid=latest_mbid, title="Weekly Jams for cofobus, week of 2026-04-27 Mon"),
            PlaylistSummary(mbid=older_mbid, title="Weekly Jams for cofobus, week of 2026-04-20 Mon"),
        ],
        playlist_mbids=(),
        title_include=("weekly-jams",),
        title_exclude=(),
    )

    assert selected == [PlaylistSummary(mbid=latest_mbid, title="Weekly Jams for cofobus, week of 2026-04-27 Mon")]
