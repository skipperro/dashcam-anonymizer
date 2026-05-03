"""Tests for FileCleanupService."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from dashcam_backend.config import CleanupConfig, StorageConfig
from dashcam_backend.file_cleanup import FileCleanupService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage_config(**overrides):
    cfg = MagicMock(spec=StorageConfig)
    cfg.bucket_raw = "raw-bucket"
    cfg.bucket_processed = "processed-bucket"
    cfg.bucket_thumbnails = "thumb-bucket"
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _make_video(video_id="vid-1", age_days=8, raw_path="raw/vid-1.mp4",
                processed_path: str = "proc/vid-1.mp4",
                thumbnail_path: str = "thumb/vid-1.jpg"):
    upload_date = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    return {
        "video_id": video_id,
        "upload_date": upload_date,
        "raw_file_path": raw_path,
        "processed_file_path": processed_path,
        "thumbnail_path": thumbnail_path,
    }


def _make_cleanup_service(enabled=True, max_age_days=7, interval_hours=1):
    cfg = CleanupConfig(enabled=enabled, max_age_days=max_age_days, interval_hours=interval_hours)
    return FileCleanupService(cleanup_config=cfg)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFileCleanupServiceDisabled:
    def test_start_does_nothing_when_disabled(self):
        svc = _make_cleanup_service(enabled=False)
        with patch.object(svc, "_run_cleanup") as mock_run:
            svc.start()
            mock_run.assert_not_called()
        assert svc._thread is None


class TestFileCleanupServiceEnabled:
    def _mock_infrastructure(self, videos):
        """Return (mock_sync_client, mock_storage, mock_config) tuple."""
        sync_client = MagicMock()
        sync_client.get_videos_older_than.return_value = videos
        sync_client.delete_tasks_for_video.return_value = None
        sync_client.delete_video_document.return_value = None

        storage = MagicMock()
        storage.s3_client = MagicMock()
        storage.s3_client.delete_object.return_value = {}

        storage_cfg = _make_storage_config()
        return sync_client, storage, storage_cfg

    def test_no_old_videos_does_nothing(self):
        svc = _make_cleanup_service()
        sync_client, storage, storage_cfg = self._mock_infrastructure([])

        with patch("dashcam_backend.file_cleanup.get_sync_mongodb_client", return_value=sync_client), \
             patch("dashcam_backend.file_cleanup.get_storage_client", return_value=storage), \
             patch("dashcam_backend.file_cleanup.get_config") as mock_cfg:
            mock_cfg.return_value.storage = storage_cfg
            mock_cfg.return_value.cleanup = svc._config
            svc._run_cleanup()

        sync_client.delete_video_document.assert_not_called()
        sync_client.delete_tasks_for_video.assert_not_called()
        storage.s3_client.delete_object.assert_not_called()

    def test_old_video_all_files_deleted(self):
        video = _make_video()
        svc = _make_cleanup_service()
        sync_client, storage, storage_cfg = self._mock_infrastructure([video])

        with patch("dashcam_backend.file_cleanup.get_sync_mongodb_client", return_value=sync_client), \
             patch("dashcam_backend.file_cleanup.get_storage_client", return_value=storage), \
             patch("dashcam_backend.file_cleanup.get_config") as mock_cfg:
            mock_cfg.return_value.storage = storage_cfg
            mock_cfg.return_value.cleanup = svc._config
            svc._run_cleanup()

        # All three storage objects deleted
        assert storage.s3_client.delete_object.call_count == 3
        storage.s3_client.delete_object.assert_any_call(Bucket="raw-bucket", Key="raw/vid-1.mp4")
        storage.s3_client.delete_object.assert_any_call(Bucket="processed-bucket", Key="proc/vid-1.mp4")
        storage.s3_client.delete_object.assert_any_call(Bucket="thumb-bucket", Key="thumb/vid-1.jpg")

        # DB cleanup
        sync_client.delete_tasks_for_video.assert_called_once_with("vid-1")
        sync_client.delete_video_document.assert_called_once_with("vid-1")

    def test_partial_paths_skip_missing_objects(self):
        """Video with no processed_file_path and no thumbnail should only delete raw."""
        video = _make_video()
        video["processed_file_path"] = None
        video["thumbnail_path"] = None
        svc = _make_cleanup_service()
        sync_client, storage, storage_cfg = self._mock_infrastructure([video])

        with patch("dashcam_backend.file_cleanup.get_sync_mongodb_client", return_value=sync_client), \
             patch("dashcam_backend.file_cleanup.get_storage_client", return_value=storage), \
             patch("dashcam_backend.file_cleanup.get_config") as mock_cfg:
            mock_cfg.return_value.storage = storage_cfg
            mock_cfg.return_value.cleanup = svc._config
            svc._run_cleanup()

        assert storage.s3_client.delete_object.call_count == 1
        storage.s3_client.delete_object.assert_called_once_with(Bucket="raw-bucket", Key="raw/vid-1.mp4")
        sync_client.delete_video_document.assert_called_once_with("vid-1")

    def test_storage_error_does_not_abort_db_cleanup(self):
        """A MinIO failure on one file must not prevent the document from being deleted."""
        video = _make_video()
        svc = _make_cleanup_service()
        sync_client, storage, storage_cfg = self._mock_infrastructure([video])
        storage.s3_client.delete_object.side_effect = Exception("MinIO down")

        with patch("dashcam_backend.file_cleanup.get_sync_mongodb_client", return_value=sync_client), \
             patch("dashcam_backend.file_cleanup.get_storage_client", return_value=storage), \
             patch("dashcam_backend.file_cleanup.get_config") as mock_cfg:
            mock_cfg.return_value.storage = storage_cfg
            mock_cfg.return_value.cleanup = svc._config
            svc._run_cleanup()

        # Document still deleted despite storage failures
        sync_client.delete_video_document.assert_called_once_with("vid-1")
        sync_client.delete_tasks_for_video.assert_called_once_with("vid-1")

    def test_multiple_videos_all_cleaned(self):
        videos = [_make_video(video_id=f"vid-{i}") for i in range(3)]
        svc = _make_cleanup_service()
        sync_client, storage, storage_cfg = self._mock_infrastructure(videos)

        with patch("dashcam_backend.file_cleanup.get_sync_mongodb_client", return_value=sync_client), \
             patch("dashcam_backend.file_cleanup.get_storage_client", return_value=storage), \
             patch("dashcam_backend.file_cleanup.get_config") as mock_cfg:
            mock_cfg.return_value.storage = storage_cfg
            mock_cfg.return_value.cleanup = svc._config
            svc._run_cleanup()

        assert sync_client.delete_video_document.call_count == 3
        assert sync_client.delete_tasks_for_video.call_count == 3
        assert storage.s3_client.delete_object.call_count == 9  # 3 files × 3 videos

    def test_max_age_days_passed_to_db_query(self):
        svc = _make_cleanup_service(max_age_days=14)
        sync_client, storage, storage_cfg = self._mock_infrastructure([])

        with patch("dashcam_backend.file_cleanup.get_sync_mongodb_client", return_value=sync_client), \
             patch("dashcam_backend.file_cleanup.get_storage_client", return_value=storage), \
             patch("dashcam_backend.file_cleanup.get_config") as mock_cfg:
            mock_cfg.return_value.storage = storage_cfg
            mock_cfg.return_value.cleanup = svc._config
            svc._run_cleanup()

        sync_client.get_videos_older_than.assert_called_once_with(14)


class TestCleanupConfig:
    def test_defaults(self):
        cfg = CleanupConfig()
        assert cfg.enabled is True
        assert cfg.max_age_days == 7
        assert cfg.interval_hours == 1

    def test_from_env_reads_variables(self, monkeypatch):
        monkeypatch.setenv("FILE_CLEANUP_ENABLED", "false")
        monkeypatch.setenv("FILE_CLEANUP_MAX_AGE_DAYS", "30")
        monkeypatch.setenv("FILE_CLEANUP_INTERVAL_HOURS", "6")
        cfg = CleanupConfig.from_env()
        assert cfg.enabled is False
        assert cfg.max_age_days == 30
        assert cfg.interval_hours == 6

    def test_backend_config_includes_cleanup(self):
        from dashcam_backend.config import BackendConfig
        cfg = BackendConfig.from_env()
        assert cfg.cleanup is not None
        assert isinstance(cfg.cleanup, CleanupConfig)
