"""Periodic service that deletes video files and records older than the configured TTL."""

import threading
from typing import Optional

from .config import get_config, CleanupConfig
from .logging import get_logger
from .mongodb_sync_client import get_sync_mongodb_client
from .storage_client import get_storage_client


logger = get_logger(__name__)


class FileCleanupService:
    """
    Background service that deletes old videos on startup and then every
    FILE_CLEANUP_INTERVAL_HOURS hours.

    For each expired video it:
    1. Deletes the raw file from MinIO (dashcam-raw-videos).
    2. Deletes the processed file from MinIO (dashcam-processed-videos), if present.
    3. Deletes the thumbnail from MinIO (dashcam-thumbnails), if present.
    4. Deletes all TaskDocuments for the video.
    5. Hard-deletes the VideoDocument from MongoDB.

    A per-file storage error never aborts the whole run — the document is still
    deleted so orphaned objects don't block future cleanup attempts.
    """

    def __init__(self, cleanup_config: Optional[CleanupConfig] = None):
        self._config = cleanup_config or get_config().cleanup
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Run an immediate cleanup tick, then start the periodic background thread."""
        if not self._config.enabled:
            logger.info("FileCleanupService disabled — skipping")
            return

        logger.info(
            "FileCleanupService starting",
            max_age_days=self._config.max_age_days,
            interval_hours=self._config.interval_hours,
        )

        # Run first tick synchronously before launching the thread so that
        # stale files are removed as soon as the backend starts.
        self._run_cleanup()

        self._thread = threading.Thread(
            target=self._cleanup_loop,
            name="file-cleanup",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the background thread to stop."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cleanup_loop(self) -> None:
        interval_seconds = self._config.interval_hours * 3600
        while not self._stop_event.wait(interval_seconds):
            try:
                self._run_cleanup()
            except Exception as exc:
                logger.error("FileCleanupService run failed", error=str(exc))

    def _run_cleanup(self) -> None:
        sync_client = get_sync_mongodb_client()
        storage = get_storage_client()
        storage_cfg = get_config().storage

        old_videos = sync_client.get_videos_older_than(self._config.max_age_days)
        if not old_videos:
            logger.debug("FileCleanupService: no expired videos found")
            return

        logger.info("FileCleanupService: found expired videos", count=len(old_videos))

        for video in old_videos:
            video_id = video.get("video_id", "unknown")
            self._delete_video(video, video_id, sync_client, storage, storage_cfg)

    def _delete_video(self, video: dict, video_id: str, sync_client, storage, storage_cfg) -> None:
        """Delete all storage objects and DB records for one video."""
        # 1. Raw file
        raw_path: Optional[str] = video.get("raw_file_path")
        if raw_path:
            self._delete_storage_object(storage, storage_cfg.bucket_raw, raw_path, video_id, "raw")

        # 2. Processed file
        processed_path: Optional[str] = video.get("processed_file_path")
        if processed_path:
            self._delete_storage_object(storage, storage_cfg.bucket_processed, processed_path, video_id, "processed")

        # 3. Thumbnail
        thumbnail_path: Optional[str] = video.get("thumbnail_path")
        if thumbnail_path:
            self._delete_storage_object(storage, storage_cfg.bucket_thumbnails, thumbnail_path, video_id, "thumbnail")

        # 4. Task documents
        try:
            sync_client.delete_tasks_for_video(video_id)
        except Exception as exc:
            logger.error("FileCleanupService: failed to delete tasks", video_id=video_id, error=str(exc))
            # Continue — still remove the video document

        # 5. Video document
        try:
            sync_client.delete_video_document(video_id)
            logger.info("FileCleanupService: deleted expired video", video_id=video_id)
        except Exception as exc:
            logger.error("FileCleanupService: failed to delete video document", video_id=video_id, error=str(exc))

    @staticmethod
    def _delete_storage_object(storage, bucket: str, key: str, video_id: str, label: str) -> None:
        """Attempt to delete one object from MinIO; log and continue on failure."""
        try:
            storage.s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info(
                "FileCleanupService: deleted storage object",
                video_id=video_id,
                type=label,
                bucket=bucket,
                key=key,
            )
        except Exception as exc:
            logger.warning(
                "FileCleanupService: could not delete storage object (continuing)",
                video_id=video_id,
                type=label,
                bucket=bucket,
                key=key,
                error=str(exc),
            )
