from __future__ import annotations

import logging
import re
from collections.abc import Sequence

import httpx

from listenbrainz_lidarr_sync.config import Config
from listenbrainz_lidarr_sync.json_types import JsonMapping, as_bool, as_int, as_list, as_mapping, as_str
from listenbrainz_lidarr_sync.models import ArtistDefaults, LidarrAlbum, LidarrArtist, ResolvedAlbum

log = logging.getLogger(__name__)
TITLE_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9]+")


class LidarrClient:
    def __init__(self, client: httpx.Client, *, config: Config, dry_run: bool = False) -> None:
        self._client = client
        self._config = config
        self._dry_run = dry_run
        self._artist_cache: dict[str, LidarrArtist | None] = {}
        self._album_cache: dict[tuple[int, str], LidarrAlbum | None] = {}
        self._artist_albums_cache: dict[int, list[LidarrAlbum]] = {}

    def get_artist_defaults(self) -> ArtistDefaults:
        response = self._client.get("/api/v1/rootfolder")
        response.raise_for_status()
        roots = [root for item in as_list(response.json()) if (root := _root_from_value(item)) is not None]
        if not roots:
            raise ValueError("Lidarr has no root folders configured.")

        selected = self._select_root(roots)
        root_path = as_str(selected.get("path"))
        if root_path is None:
            raise ValueError("Selected Lidarr root folder does not include a path.")

        quality_profile_id = self._config.lidarr_quality_profile_id or as_int(selected.get("defaultQualityProfileId"))
        metadata_profile_id = self._config.lidarr_metadata_profile_id or as_int(
            selected.get("defaultMetadataProfileId")
        )
        if quality_profile_id is None:
            raise ValueError("Set LISTENBRAINZ_LIDARR_SYNC_LIDARR_QUALITY_PROFILE_ID or a root folder default.")
        if metadata_profile_id is None:
            raise ValueError("Set LISTENBRAINZ_LIDARR_SYNC_LIDARR_METADATA_PROFILE_ID or a root folder default.")
        return ArtistDefaults(
            root_folder_path=root_path,
            quality_profile_id=quality_profile_id,
            metadata_profile_id=metadata_profile_id,
        )

    def get_artist_by_mbid(self, mbid: str) -> LidarrArtist | None:
        if mbid in self._artist_cache:
            return self._artist_cache[mbid]
        response = self._client.get("/api/v1/artist", params={"mbId": mbid})
        response.raise_for_status()
        for value in as_list(response.json()):
            artist = _artist_from_value(value)
            if artist is not None and artist.mbid == mbid:
                self._artist_cache[mbid] = artist
                return artist
        self._artist_cache[mbid] = None
        return None

    def add_artist_by_mbid(self, mbid: str, defaults: ArtistDefaults) -> LidarrArtist | None:
        lookup_response = self._client.get("/api/v1/artist/lookup", params={"term": f"lidarr:{mbid}"})
        lookup_response.raise_for_status()
        lookup = _first_artist_lookup(as_list(lookup_response.json()), mbid=mbid)
        if lookup is None:
            log.warning("Lidarr lookup did not return artist %s", mbid)
            return None

        payload = dict(lookup)
        payload.update(
            {
                "rootFolderPath": defaults.root_folder_path,
                "qualityProfileId": defaults.quality_profile_id,
                "metadataProfileId": defaults.metadata_profile_id,
                "monitored": self._config.artist_monitored,
                "monitorNewItems": self._config.artist_monitor_new_items.value,
                "addOptions": {
                    "monitor": self._config.artist_add_monitor.value,
                    "monitored": self._config.artist_monitored,
                    "searchForMissingAlbums": self._config.search_for_missing_albums,
                },
            }
        )
        if self._dry_run:
            log.info("Dry run: would add Lidarr artist %s", mbid)
            artist = _artist_from_mapping(payload)
            self._artist_cache[mbid] = artist
            return artist

        response = self._client.post("/api/v1/artist", json=payload)
        response.raise_for_status()
        artist = _artist_from_value(response.json())
        self._artist_cache[mbid] = artist
        return artist

    def get_album(self, *, artist_id: int, release_group_mbid: str) -> LidarrAlbum | None:
        cache_key = (artist_id, release_group_mbid)
        if cache_key in self._album_cache:
            return self._album_cache[cache_key]
        response = self._client.get(
            "/api/v1/album",
            params={
                "artistId": artist_id,
                "foreignAlbumId": release_group_mbid,
                "includeAllArtistAlbums": "true",
            },
        )
        response.raise_for_status()
        for value in as_list(response.json()):
            album = _album_from_value(value)
            if album is not None and album.foreign_album_id == release_group_mbid:
                self._album_cache[cache_key] = album
                return album
        self._album_cache[cache_key] = None
        return None

    def get_artist_albums(self, artist_id: int) -> list[LidarrAlbum]:
        if artist_id in self._artist_albums_cache:
            return self._artist_albums_cache[artist_id]
        response = self._client.get(
            "/api/v1/album",
            params={
                "artistId": artist_id,
                "includeAllArtistAlbums": "true",
            },
        )
        response.raise_for_status()
        albums = [album for item in as_list(response.json()) if (album := _album_from_value(item)) is not None]
        self._artist_albums_cache[artist_id] = albums
        for album in albums:
            self._album_cache[(artist_id, album.foreign_album_id)] = album
        return albums

    def find_artist_album_by_title(self, *, artist_id: int, title: str) -> LidarrAlbum | None:
        normalized_title = normalize_title(title)
        for album in self.get_artist_albums(artist_id):
            if normalize_title(album.title) == normalized_title:
                return album
        return None

    def mark_album_wanted(self, album: LidarrAlbum) -> None:
        if self._dry_run:
            log.info("Dry run: would mark Lidarr album %s wanted", album.foreign_album_id)
            return
        response = self._client.put("/api/v1/album/monitor", json={"albumIds": [album.id], "monitored": True})
        response.raise_for_status()

    def search_album(self, album: LidarrAlbum) -> None:
        if self._dry_run:
            log.info("Dry run: would trigger Lidarr album search for %s", album.foreign_album_id)
            return
        response = self._client.post("/api/v1/command", json={"name": "AlbumSearch", "albumIds": [album.id]})
        response.raise_for_status()

    def ensure_artist_for_album(
        self,
        album: ResolvedAlbum,
        defaults: ArtistDefaults,
    ) -> tuple[LidarrArtist | None, bool]:
        for artist_mbid in album.artist_mbids:
            artist = self.get_artist_by_mbid(artist_mbid)
            if artist is not None:
                return artist, False
        for artist_mbid in album.artist_mbids:
            artist = self.add_artist_by_mbid(artist_mbid, defaults)
            if artist is not None:
                return artist, True
        return None, False

    def _select_root(self, roots: Sequence[JsonMapping]) -> JsonMapping:
        configured_path = self._config.lidarr_root_folder_path
        if configured_path is not None:
            for root in roots:
                if as_str(root.get("path")) == configured_path:
                    return root
            raise ValueError(f"Lidarr root folder not found: {configured_path}")
        if len(roots) == 1:
            return roots[0]
        raise ValueError("Multiple Lidarr root folders exist; set LISTENBRAINZ_LIDARR_SYNC_LIDARR_ROOT_FOLDER_PATH.")


def create_http_client(*, config: Config) -> httpx.Client:
    return httpx.Client(
        base_url=config.lidarr_url,
        timeout=30.0,
        headers={"X-Api-Key": config.lidarr_api_key},
    )


def _root_from_value(value: object) -> JsonMapping | None:
    if isinstance(value, dict):
        return value
    return None


def _first_artist_lookup(values: Sequence[object], *, mbid: str) -> JsonMapping | None:
    for value in values:
        if not isinstance(value, dict):
            continue
        if as_str(value.get("foreignArtistId")) == mbid or as_str(value.get("mbId")) == mbid:
            return value
    return None


def _artist_from_value(value: object) -> LidarrArtist | None:
    if not isinstance(value, dict):
        return None
    return _artist_from_mapping(value)


def _artist_from_mapping(value: JsonMapping) -> LidarrArtist | None:
    artist_id = as_int(value.get("id"))
    mbid = as_str(value.get("foreignArtistId")) or as_str(value.get("mbId"))
    if artist_id is None or mbid is None:
        return None
    name = as_str(value.get("artistName")) or mbid
    return LidarrArtist(id=artist_id, mbid=mbid, name=name)


def _album_from_value(value: object) -> LidarrAlbum | None:
    if not isinstance(value, dict):
        return None
    album_id = as_int(value.get("id"))
    foreign_album_id = as_str(value.get("foreignAlbumId"))
    statistics_value = value.get("statistics")
    statistics = as_mapping(statistics_value, "Lidarr album statistics") if isinstance(statistics_value, dict) else {}
    track_file_count = as_int(statistics.get("trackFileCount")) or 0
    if album_id is None or foreign_album_id is None:
        return None
    title = as_str(value.get("title")) or foreign_album_id
    return LidarrAlbum(
        id=album_id,
        foreign_album_id=foreign_album_id,
        title=title,
        monitored=as_bool(value.get("monitored")),
        track_file_count=track_file_count,
    )


def normalize_title(value: str) -> str:
    return TITLE_SEPARATOR_PATTERN.sub(" ", value.casefold()).strip()
