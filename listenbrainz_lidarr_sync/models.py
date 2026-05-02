from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlaylistSummary:
    mbid: str
    title: str


@dataclass(frozen=True, slots=True)
class TrackReference:
    recording_mbid: str | None
    release_mbid: str | None
    release_group_mbid: str | None
    artist_mbids: tuple[str, ...]
    title: str
    album: str | None


@dataclass(frozen=True, slots=True)
class ResolvedAlbum:
    release_group_mbid: str
    artist_mbids: tuple[str, ...]
    title: str


@dataclass(frozen=True, slots=True)
class ArtistDefaults:
    root_folder_path: str
    quality_profile_id: int
    metadata_profile_id: int


@dataclass(frozen=True, slots=True)
class LidarrArtist:
    id: int
    mbid: str
    name: str


@dataclass(frozen=True, slots=True)
class LidarrAlbum:
    id: int
    foreign_album_id: str
    title: str
    monitored: bool
    track_file_count: int


@dataclass(frozen=True, slots=True)
class SyncStats:
    playlists_seen: int = 0
    tracks_seen: int = 0
    albums_resolved: int = 0
    artists_added: int = 0
    albums_marked_wanted: int = 0
    album_searches_triggered: int = 0
    albums_skipped_wanted: int = 0
    albums_skipped_downloaded: int = 0
    albums_skipped_missing_in_lidarr: int = 0
