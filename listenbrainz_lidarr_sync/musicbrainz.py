from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

import musicbrainzngs

from listenbrainz_lidarr_sync.json_types import JsonMapping, JsonValue, as_list, as_mapping, as_str
from listenbrainz_lidarr_sync.models import ResolvedAlbum, TrackReference

RELEASE_INCLUDES = ["release-groups", "artist-credits"]
RECORDING_INCLUDES = ["artists", "releases", "artist-credits"]


class MusicBrainzLookup(Protocol):
    def get_release_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]: ...

    def get_recording_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]: ...


class MusicBrainzNgsLookup:
    def __init__(self) -> None:
        musicbrainzngs.set_useragent(
            "listenbrainz-lidarr-sync",
            "0.1.0",
            "https://github.com/cofob/listenbrainz-lidarr-sync",
        )

    def get_release_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        return musicbrainzngs.get_release_by_id(mbid, includes=list(includes))

    def get_recording_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        return musicbrainzngs.get_recording_by_id(mbid, includes=list(includes))


class MusicBrainzResolver:
    def __init__(self, lookup: MusicBrainzLookup) -> None:
        self._lookup = lookup
        self._release_cache: dict[str, ResolvedAlbum | None] = {}
        self._recording_cache: dict[str, ResolvedAlbum | None] = {}

    def resolve_track(self, track: TrackReference) -> ResolvedAlbum | None:
        if track.release_group_mbid is not None and track.artist_mbids:
            return ResolvedAlbum(
                release_group_mbid=track.release_group_mbid,
                artist_mbids=track.artist_mbids,
                title=track.album or track.title,
            )

        if track.release_mbid is not None:
            resolved = self._resolve_release(track.release_mbid)
            if resolved is not None:
                return resolved

        if track.recording_mbid is None:
            return None

        if track.recording_mbid in self._recording_cache:
            return self._recording_cache[track.recording_mbid]

        recording = as_mapping(
            dict(self._lookup.get_recording_by_id(track.recording_mbid, includes=RECORDING_INCLUDES)),
            "MusicBrainz recording",
        )
        recording_body = as_mapping(recording.get("recording"), "MusicBrainz recording body")
        resolved = _resolved_from_recording(recording_body)
        if resolved is not None:
            self._recording_cache[track.recording_mbid] = resolved
            return resolved

        release_mbid = _release_mbid_from_recording(recording_body)
        if release_mbid is None:
            self._recording_cache[track.recording_mbid] = None
            return None
        resolved = self._resolve_release(release_mbid)
        self._recording_cache[track.recording_mbid] = resolved
        return resolved

    def _resolve_release(self, release_mbid: str) -> ResolvedAlbum | None:
        if release_mbid in self._release_cache:
            return self._release_cache[release_mbid]
        release = as_mapping(
            dict(self._lookup.get_release_by_id(release_mbid, includes=RELEASE_INCLUDES)),
            "MusicBrainz release",
        )
        resolved = _resolved_from_release(as_mapping(release.get("release"), "MusicBrainz release body"))
        self._release_cache[release_mbid] = resolved
        return resolved


def _resolved_from_release(release: JsonMapping) -> ResolvedAlbum | None:
    release_group = release.get("release-group")
    if not isinstance(release_group, dict):
        return None
    release_group_mbid = as_str(release_group.get("id"))
    if release_group_mbid is None:
        return None
    return ResolvedAlbum(
        release_group_mbid=release_group_mbid,
        artist_mbids=_artist_credit_mbids(release),
        title=as_str(release_group.get("title")) or as_str(release.get("title")) or release_group_mbid,
    )


def _resolved_from_recording(recording: JsonMapping) -> ResolvedAlbum | None:
    releases = as_list(recording.get("release-list"))
    for release_value in releases:
        if not isinstance(release_value, dict):
            continue
        resolved = _resolved_from_release(release_value)
        if resolved is not None:
            return resolved
    return None


def _release_mbid_from_recording(recording: JsonMapping) -> str | None:
    for release_value in as_list(recording.get("release-list")):
        if not isinstance(release_value, dict):
            continue
        release_mbid = as_str(release_value.get("id"))
        if release_mbid is not None:
            return release_mbid
    return None


def _artist_credit_mbids(mapping: JsonMapping) -> tuple[str, ...]:
    mbids: list[str] = []
    for credit_value in as_list(mapping.get("artist-credit")):
        if not isinstance(credit_value, dict):
            continue
        artist = credit_value.get("artist")
        if not isinstance(artist, dict):
            continue
        artist_mbid = as_str(artist.get("id"))
        if artist_mbid is not None:
            mbids.append(artist_mbid)
    return tuple(mbids)
