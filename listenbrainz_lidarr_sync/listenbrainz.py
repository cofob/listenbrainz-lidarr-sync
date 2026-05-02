from __future__ import annotations

import re
from collections.abc import Iterable

import httpx

from listenbrainz_lidarr_sync.config import extract_mbid
from listenbrainz_lidarr_sync.json_types import (
    JsonMapping,
    JsonValue,
    as_list,
    as_mapping,
    as_str,
    maybe_mapping,
    string_values,
)
from listenbrainz_lidarr_sync.models import PlaylistSummary, TrackReference

DEFAULT_PAGE_SIZE = 100
MB_URL_PATTERN = re.compile(
    r"musicbrainz\.org/(?P<entity>recording|release|artist)/"
    r"(?P<mbid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)
TITLE_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9]+")


class ListenBrainzClient:
    def __init__(self, client: httpx.Client, *, user: str, token: str | None = None) -> None:
        self._client = client
        self._user = user
        self._token = token

    def get_created_for_playlists(self) -> list[PlaylistSummary]:
        playlists: list[PlaylistSummary] = []
        offset = 0
        while True:
            response = self._client.get(
                f"/1/user/{self._user}/playlists/createdfor",
                params={"count": DEFAULT_PAGE_SIZE, "offset": offset},
                headers=self._headers,
            )
            response.raise_for_status()
            page = as_mapping(response.json(), "ListenBrainz createdfor playlists")
            page_playlists = parse_playlist_summaries(page)
            playlists.extend(page_playlists)
            if len(page_playlists) < DEFAULT_PAGE_SIZE:
                return playlists
            offset += DEFAULT_PAGE_SIZE

    def get_playlist_tracks(self, playlist_mbid: str) -> list[TrackReference]:
        response = self._client.get(
            f"/1/playlist/{playlist_mbid}",
            params={"fetch_metadata": "true"},
            headers=self._headers,
        )
        response.raise_for_status()
        payload = as_mapping(response.json(), "ListenBrainz playlist")
        return parse_playlist_tracks(payload)

    @property
    def _headers(self) -> dict[str, str]:
        if self._token is None:
            return {}
        return {"Authorization": f"Token {self._token}"}


def create_http_client() -> httpx.Client:
    return httpx.Client(base_url="https://api.listenbrainz.org", timeout=30.0)


def filter_playlists(
    playlists: Iterable[PlaylistSummary],
    *,
    playlist_mbids: tuple[str, ...],
    title_include: tuple[str, ...],
    title_exclude: tuple[str, ...],
) -> list[PlaylistSummary]:
    explicit = set(playlist_mbids)
    include_terms = tuple(term.casefold() for term in title_include)
    exclude_terms = tuple(term.casefold() for term in title_exclude)

    selected: list[PlaylistSummary] = []
    seen: set[str] = set()
    selected_title_match = False
    for playlist in playlists:
        if playlist.mbid in seen:
            continue
        title = playlist.title.casefold()
        title_slug = _title_slug(title)
        explicit_match = playlist.mbid in explicit
        include_match = not include_terms or any(
            _term_matches_title(term, title=title, title_slug=title_slug) for term in include_terms
        )
        exclude_match = any(_term_matches_title(term, title=title, title_slug=title_slug) for term in exclude_terms)
        if exclude_match:
            continue
        if explicit_match:
            selected.append(playlist)
            seen.add(playlist.mbid)
            continue
        if include_match and (not include_terms or not selected_title_match):
            selected.append(playlist)
            seen.add(playlist.mbid)
            selected_title_match = True
    selected.extend([PlaylistSummary(mbid=mbid, title=mbid) for mbid in playlist_mbids if mbid not in seen])
    return selected


def parse_playlist_summaries(payload: JsonMapping) -> list[PlaylistSummary]:
    return [
        summary for item in _playlist_items(payload) if (summary := _playlist_summary_from_mapping(item)) is not None
    ]


def parse_playlist_tracks(payload: JsonMapping) -> list[TrackReference]:
    playlist = _playlist_mapping(payload)
    tracks = as_list(playlist.get("track"))
    return [track for item in tracks if (track := _track_reference_from_value(item)) is not None]


def _playlist_items(payload: JsonMapping) -> list[JsonMapping]:
    playlist = _playlist_mapping(payload)
    raw_playlists = as_list(payload.get("playlists")) or as_list(playlist.get("playlists"))
    if raw_playlists:
        return [item for raw in raw_playlists if (item := _playlist_mapping_from_value(raw)) is not None]
    return [playlist]


def _term_matches_title(term: str, *, title: str, title_slug: str) -> bool:
    return term in title or _title_slug(term) in title_slug


def _title_slug(value: str) -> str:
    return TITLE_SEPARATOR_PATTERN.sub("-", value.casefold()).strip("-")


def _playlist_mapping(payload: JsonMapping) -> JsonMapping:
    nested = payload.get("playlist")
    if isinstance(nested, dict):
        return nested
    return payload


def _playlist_mapping_from_value(value: JsonValue) -> JsonMapping | None:
    if not isinstance(value, dict):
        return None
    return _playlist_mapping(value)


def _playlist_summary_from_mapping(payload: JsonMapping) -> PlaylistSummary | None:
    title = as_str(payload.get("title")) or "Untitled"
    identifiers = string_values(payload.get("identifier"))
    if not identifiers:
        raw_mbid = as_str(payload.get("playlist_mbid")) or as_str(payload.get("id"))
        if raw_mbid is None:
            return None
        return PlaylistSummary(mbid=extract_mbid(raw_mbid), title=title)
    return PlaylistSummary(mbid=extract_mbid(identifiers[0]), title=title)


def _track_reference_from_value(value: JsonValue) -> TrackReference | None:
    if not isinstance(value, dict):
        return None
    title = as_str(value.get("title")) or "Untitled"
    album = as_str(value.get("album"))
    recording_mbid = _first_entity_mbid(string_values(value.get("identifier")), entity="recording")
    extension = _track_extension(value)
    additional_metadata = maybe_mapping(extension.get("additional_metadata")) if extension is not None else None
    extension_release_identifiers = string_values(extension.get("release_identifier")) if extension is not None else ()
    extension_artist_identifiers = string_values(extension.get("artist_identifiers")) if extension is not None else ()
    release_mbid = (
        _first_entity_mbid(string_values(value.get("release_identifier")), entity="release")
        or _first_entity_mbid(extension_release_identifiers, entity="release")
        or (as_str(additional_metadata.get("caa_release_mbid")) if additional_metadata is not None else None)
    )
    release_group_mbid = (
        as_str(additional_metadata.get("release_group_mbid")) if additional_metadata is not None else None
    )
    artist_mbids = tuple(
        _entity_mbids(string_values(value.get("artist_identifiers")), entity="artist")
        or _entity_mbids(extension_artist_identifiers, entity="artist")
        or _artist_mbids_from_additional_metadata(additional_metadata)
    )
    return TrackReference(
        recording_mbid=recording_mbid,
        release_mbid=release_mbid,
        release_group_mbid=release_group_mbid,
        artist_mbids=artist_mbids,
        title=title,
        album=album,
    )


def _first_entity_mbid(values: Iterable[str], *, entity: str) -> str | None:
    for mbid in _entity_mbids(values, entity=entity):
        return mbid
    return None


def _entity_mbids(values: Iterable[str], *, entity: str) -> list[str]:
    mbids: list[str] = []
    for value in values:
        match = MB_URL_PATTERN.search(value)
        if match is not None and match.group("entity") == entity:
            mbids.append(match.group("mbid").lower())
    return mbids


def _track_extension(track: JsonMapping) -> JsonMapping | None:
    extension = maybe_mapping(track.get("extension"))
    if extension is None:
        return None
    track_extension = extension.get("https://musicbrainz.org/doc/jspf#track")
    return maybe_mapping(track_extension)


def _artist_mbids_from_additional_metadata(additional_metadata: JsonMapping | None) -> list[str]:
    if additional_metadata is None:
        return []
    artist_mbids: list[str] = []
    for artist_value in as_list(additional_metadata.get("artists")):
        artist = maybe_mapping(artist_value)
        if artist is None:
            continue
        artist_mbid = as_str(artist.get("artist_mbid"))
        if artist_mbid is not None:
            artist_mbids.append(artist_mbid)
    return artist_mbids
