from __future__ import annotations

import logging
from dataclasses import replace

from listenbrainz_lidarr_sync.config import Config
from listenbrainz_lidarr_sync.lidarr import LidarrClient
from listenbrainz_lidarr_sync.listenbrainz import ListenBrainzClient, filter_playlists
from listenbrainz_lidarr_sync.models import ArtistDefaults, LidarrAlbum, ResolvedAlbum, SyncStats, TrackReference
from listenbrainz_lidarr_sync.musicbrainz import MusicBrainzResolver

log = logging.getLogger(__name__)


class SyncService:
    def __init__(
        self,
        *,
        config: Config,
        listenbrainz: ListenBrainzClient,
        musicbrainz: MusicBrainzResolver,
        lidarr: LidarrClient,
    ) -> None:
        self._config = config
        self._listenbrainz = listenbrainz
        self._musicbrainz = musicbrainz
        self._lidarr = lidarr

    def run_once(self) -> SyncStats:
        defaults = self._lidarr.get_artist_defaults()
        playlists = filter_playlists(
            self._listenbrainz.get_created_for_playlists(),
            playlist_mbids=self._config.playlist_mbids,
            title_include=self._config.playlist_title_include,
            title_exclude=self._config.playlist_title_exclude,
        )
        stats = SyncStats(playlists_seen=len(playlists))
        seen_albums: set[str] = set()

        for playlist in playlists:
            log.info("Syncing ListenBrainz playlist %s (%s)", playlist.title, playlist.mbid)
            tracks = self._listenbrainz.get_playlist_tracks(playlist.mbid)
            stats = replace(stats, tracks_seen=stats.tracks_seen + len(tracks))
            for track in tracks:
                fast_path_stats = self._sync_track_from_lidarr_metadata(track, stats, defaults, seen_albums)
                if fast_path_stats is not None:
                    stats = fast_path_stats
                    continue

                resolved = self._musicbrainz.resolve_track(track)
                if resolved is None:
                    log.warning("Could not resolve playlist track %s to a MusicBrainz release group", track.title)
                    continue
                if resolved.release_group_mbid in seen_albums:
                    continue
                seen_albums.add(resolved.release_group_mbid)
                stats = replace(stats, albums_resolved=stats.albums_resolved + 1)
                stats = self._sync_album(resolved, stats, defaults)

        return stats

    def _sync_track_from_lidarr_metadata(
        self,
        track: TrackReference,
        stats: SyncStats,
        defaults: ArtistDefaults,
        seen_albums: set[str],
    ) -> SyncStats | None:
        if track.album is None or not track.artist_mbids:
            return None

        for artist_mbid in track.artist_mbids:
            artist = self._lidarr.get_artist_by_mbid(artist_mbid)
            if artist is None:
                continue
            lidarr_album = self._lidarr.find_artist_album_by_title(artist_id=artist.id, title=track.album)
            if lidarr_album is None:
                continue
            if lidarr_album.foreign_album_id in seen_albums:
                return stats
            seen_albums.add(lidarr_album.foreign_album_id)
            resolved = ResolvedAlbum(
                release_group_mbid=lidarr_album.foreign_album_id,
                artist_mbids=track.artist_mbids,
                title=lidarr_album.title,
            )
            return self._sync_album(resolved, replace(stats, albums_resolved=stats.albums_resolved + 1), defaults)

        return None

    def _sync_album(self, album: ResolvedAlbum, stats: SyncStats, defaults: ArtistDefaults) -> SyncStats:
        if not album.artist_mbids:
            log.warning("Skipping album %s because no artist MBIDs were resolved", album.release_group_mbid)
            return stats

        artist, artist_added = self._lidarr.ensure_artist_for_album(album, defaults)
        if artist is None:
            log.warning("Skipping album %s because no Lidarr artist could be found or added", album.release_group_mbid)
            return stats
        if artist_added:
            stats = replace(stats, artists_added=stats.artists_added + 1)

        lidarr_album = self._lidarr.get_album(artist_id=artist.id, release_group_mbid=album.release_group_mbid)
        if lidarr_album is None:
            log.warning("Lidarr artist %s does not expose album %s", artist.name, album.release_group_mbid)
            return replace(stats, albums_skipped_missing_in_lidarr=stats.albums_skipped_missing_in_lidarr + 1)
        return self._sync_lidarr_album(lidarr_album, stats)

    def _sync_lidarr_album(self, lidarr_album: LidarrAlbum, stats: SyncStats) -> SyncStats:
        if lidarr_album.track_file_count > 0:
            return replace(stats, albums_skipped_downloaded=stats.albums_skipped_downloaded + 1)
        if lidarr_album.monitored:
            return replace(stats, albums_skipped_wanted=stats.albums_skipped_wanted + 1)

        self._lidarr.mark_album_wanted(lidarr_album)
        return replace(stats, albums_marked_wanted=stats.albums_marked_wanted + 1)
