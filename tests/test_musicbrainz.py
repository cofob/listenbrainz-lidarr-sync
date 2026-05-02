from __future__ import annotations

from collections.abc import Mapping, Sequence

from listenbrainz_lidarr_sync.json_types import JsonValue
from listenbrainz_lidarr_sync.models import TrackReference
from listenbrainz_lidarr_sync.musicbrainz import MusicBrainzResolver

RELEASE_MBID = "189002e7-3285-4e2e-92a3-7f6c30d407a2"
RELEASE_GROUP_MBID = "e66b3779-0944-4fd6-9f2f-45f6285532c6"
ARTIST_MBID = "0383dadf-2a4e-4d10-a46a-e9e041da8eb3"


class FakeLookup:
    def get_release_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        assert mbid == RELEASE_MBID
        assert "release-groups" in includes
        return {
            "release": {
                "id": RELEASE_MBID,
                "title": "Release Title",
                "release-group": {"id": RELEASE_GROUP_MBID, "title": "Album Title"},
                "artist-credit": [{"artist": {"id": ARTIST_MBID}}],
            }
        }

    def get_recording_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        raise AssertionError(f"release lookup should be preferred over {mbid} with {includes}")


class RecordingOnlyLookup:
    def get_release_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        assert mbid == RELEASE_MBID
        assert "release-groups" in includes
        return {
            "release": {
                "id": RELEASE_MBID,
                "title": "Release Title",
                "release-group": {"id": RELEASE_GROUP_MBID, "title": "Album Title"},
                "artist-credit": [{"artist": {"id": ARTIST_MBID}}],
            }
        }

    def get_recording_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        assert mbid == "b1a9c0e9-d987-4042-ae91-78d6a3267d69"
        assert "release-groups" not in includes
        return {
            "recording": {
                "id": mbid,
                "title": "Track",
                "release-list": [{"id": RELEASE_MBID, "title": "Release Title"}],
            }
        }


class UnusedLookup:
    def get_release_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        raise AssertionError(f"release lookup should not be used for {mbid} with {includes}")

    def get_recording_by_id(self, mbid: str, *, includes: Sequence[str]) -> Mapping[str, JsonValue]:
        raise AssertionError(f"recording lookup should not be used for {mbid} with {includes}")


def test_resolver_prefers_release_identifier() -> None:
    resolver = MusicBrainzResolver(FakeLookup())
    track = TrackReference(
        recording_mbid=None,
        release_mbid=RELEASE_MBID,
        release_group_mbid=None,
        artist_mbids=(),
        title="Track",
        album=None,
    )

    resolved = resolver.resolve_track(track)

    assert resolved is not None
    assert resolved.release_group_mbid == RELEASE_GROUP_MBID


def test_resolver_uses_pre_resolved_release_group_without_lookup() -> None:
    resolver = MusicBrainzResolver(UnusedLookup())
    track = TrackReference(
        recording_mbid="b1a9c0e9-d987-4042-ae91-78d6a3267d69",
        release_mbid=RELEASE_MBID,
        release_group_mbid=RELEASE_GROUP_MBID,
        artist_mbids=(ARTIST_MBID,),
        title="Track",
        album="Album Title",
    )

    resolved = resolver.resolve_track(track)

    assert resolved is not None
    assert resolved.release_group_mbid == RELEASE_GROUP_MBID
    assert resolved.artist_mbids == (ARTIST_MBID,)
    assert resolved.title == "Album Title"
    assert resolved.artist_mbids == (ARTIST_MBID,)
    assert resolved.title == "Album Title"


def test_resolver_uses_release_lookup_for_recording_release_group() -> None:
    resolver = MusicBrainzResolver(RecordingOnlyLookup())
    track = TrackReference(
        recording_mbid="b1a9c0e9-d987-4042-ae91-78d6a3267d69",
        release_mbid=None,
        release_group_mbid=None,
        artist_mbids=(),
        title="Track",
        album=None,
    )

    resolved = resolver.resolve_track(track)

    assert resolved is not None
    assert resolved.release_group_mbid == RELEASE_GROUP_MBID
