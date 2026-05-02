from __future__ import annotations

import argparse
import logging
import time

from listenbrainz_lidarr_sync.config import Config, load_config_from_env
from listenbrainz_lidarr_sync.lidarr import LidarrClient
from listenbrainz_lidarr_sync.lidarr import create_http_client as create_lidarr_http_client
from listenbrainz_lidarr_sync.listenbrainz import ListenBrainzClient
from listenbrainz_lidarr_sync.listenbrainz import create_http_client as create_listenbrainz_http_client
from listenbrainz_lidarr_sync.models import SyncStats
from listenbrainz_lidarr_sync.musicbrainz import MusicBrainzNgsLookup, MusicBrainzResolver
from listenbrainz_lidarr_sync.sync import SyncService
from listenbrainz_lidarr_sync.telegram import build_reporter

log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true", help="Run forever and sleep between sync passes.")
    parser.add_argument("--dry-run", action="store_true", help="Log Lidarr writes without applying them.")
    parser.add_argument("--interval-seconds", type=int, help="Sleep interval for --watch.")
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s (%(name)s): %(message)s",
    )
    logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)


def build_service(config: Config, *, dry_run: bool) -> SyncService:
    listenbrainz_http = create_listenbrainz_http_client()
    lidarr_http = create_lidarr_http_client(config=config)
    return SyncService(
        config=config,
        listenbrainz=ListenBrainzClient(
            listenbrainz_http,
            user=config.listenbrainz_user,
            token=config.listenbrainz_token,
        ),
        musicbrainz=MusicBrainzResolver(MusicBrainzNgsLookup()),
        lidarr=LidarrClient(lidarr_http, config=config, dry_run=dry_run),
    )


def run_sync(config: Config, *, dry_run: bool) -> SyncStats:
    service = build_service(config, dry_run=dry_run)
    stats = service.run_once()
    log.info(
        "Finished sync: playlists=%s tracks=%s resolved_albums=%s artists_added=%s albums_marked_wanted=%s "
        "album_searches_triggered=%s skipped_wanted=%s skipped_downloaded=%s skipped_missing_in_lidarr=%s",
        stats.playlists_seen,
        stats.tracks_seen,
        stats.albums_resolved,
        stats.artists_added,
        stats.albums_marked_wanted,
        stats.album_searches_triggered,
        stats.albums_skipped_wanted,
        stats.albums_skipped_downloaded,
        stats.albums_skipped_missing_in_lidarr,
    )
    return stats


def main() -> None:
    configure_logging()
    args = parse_args()
    config = load_config_from_env()
    reporter = build_reporter(config)
    interval_seconds = args.interval_seconds or config.interval_seconds
    if interval_seconds <= 0:
        raise ValueError("--interval-seconds must be greater than zero.")

    while True:
        try:
            stats = run_sync(config, dry_run=args.dry_run)
        except Exception as exc:
            if reporter is not None and config.telegram_report_failure:
                reporter.send_failure(exc, dry_run=args.dry_run)
            raise
        if reporter is not None and config.telegram_report_success:
            reporter.send_success(stats, dry_run=args.dry_run)
        if not args.watch:
            return
        log.info("Sleeping for %s seconds before next sync", interval_seconds)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
