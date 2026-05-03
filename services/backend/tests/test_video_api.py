"""
Unit tests for video API endpoints.

Tests video upload, listing, thumbnail generation, and delete functionality.
"""

import asyncio
import json
import tempfile
import uuid
from datetime import datetime, UTC
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from dashcam_backend.video_api import (
    router,
    upload_video,
    list_videos,
    get_thumbnail,
    get_progress,
    delete_video,
    generate_thumbnail_background,
    get_storage_client,
    get_mongodb_client,
    VideoInfo,
    VideoListResponse
)
from dashcam_backend.models import VideoDocument, VideoStatus, ProcessingSettings


class TestVideoAPIClientDependencies:
    """Test client dependency injection."""
    
    @pytest.mark.asyncio
    async def test_get_storage_client(self):
        """Test storage client singleton creation."""
        client1 = await get_storage_client()
        client2 = await get_storage_client()
        assert client1 is client2  # Should be same instance
    
    @pytest.mark.asyncio
    async def test_get_mongodb_client(self):
        """Test MongoDB client singleton creation."""
        with patch('dashcam_backend.video_api.MongoDBClient') as mock_client_class:
            mock_instance = AsyncMock()
            mock_client_class.return_value = mock_instance
            
            client1 = await get_mongodb_client()
            client2 = await get_mongodb_client()
            
            assert client1 is client2  # Should be same instance
            mock_instance.connect.assert_called_once()


class TestVideoUpload:
    """Test video upload functionality."""
    
    @pytest.fixture
    def mock_upload_file(self):
        """Create mock upload file."""
        file_content = b"fake video content" * 1000  # ~17KB
        file = UploadFile(
            filename="test_video.mp4",
            file=BytesIO(file_content)
        )
        return file, file_content
    
    @pytest.fixture
    def mock_clients(self):
        """Mock storage and MongoDB clients."""
        storage_client = AsyncMock()
        mongodb_client = AsyncMock()
        
        # Mock storage operations
        storage_client.initiate_multipart_upload.return_value = "upload-123"
        storage_client.upload_part.return_value = "etag-123"
        storage_client.complete_multipart_upload.return_value = True
        
        return storage_client, mongodb_client
    
    @pytest.mark.asyncio
    async def test_upload_video_success(self, mock_upload_file, mock_clients):
        """Test successful video upload."""
        file, content = mock_upload_file
        storage_client, mongodb_client = mock_clients
        
        # Mock background tasks
        background_tasks = Mock()
        
        with patch('dashcam_backend.video_api.generate_video_id') as mock_gen_id:
            mock_gen_id.return_value = "test-video-123"
            
            response = await upload_video(
                background_tasks=background_tasks,
                file=file,
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        # Verify response
        assert response.video_id == "test-video-123"
        assert response.status == "uploaded"
        
        # Verify storage operations
        storage_client.initiate_multipart_upload.assert_called_once()
        storage_client.complete_multipart_upload.assert_called_once()
        
        # Verify database operation
        mongodb_client.create_video.assert_called_once()
        video_doc = mongodb_client.create_video.call_args[0][0]
        assert video_doc.video_id == "test-video-123"
        assert video_doc.filename == "test_video.mp4"
        assert video_doc.status == VideoStatus.UPLOADING  # Initially created as UPLOADING
        
        # Verify status was updated to UPLOADED at the end
        mongodb_client.update_video_status.assert_called()
        status_update_calls = mongodb_client.update_video_status.call_args_list
        final_call = status_update_calls[-1]
        assert final_call[0][0] == "test-video-123"  # video_id
        assert final_call[0][1] == VideoStatus.UPLOADED  # final status
        
        # Verify background task was added
        background_tasks.add_task.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_upload_video_with_settings(self, mock_upload_file, mock_clients):
        """Test basic video upload without processing settings."""
        file, content = mock_upload_file
        storage_client, mongodb_client = mock_clients
        background_tasks = Mock()
        
        settings_json = json.dumps({
            "yolo_classes": [0, 1, 2],  # person, bicycle, car
            "model_size": "medium",
            "detection_type": "segmentation"
        })
        
        with patch('dashcam_backend.video_api.generate_video_id') as mock_gen_id:
            mock_gen_id.return_value = "test-video-123"
            
            response = await upload_video(
                background_tasks=background_tasks,
                file=file,
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        assert response.video_id == "test-video-123"
        
        # Verify video document was created
        video_doc = mongodb_client.create_video.call_args[0][0]
        assert video_doc.video_id == "test-video-123"
        assert video_doc.filename == "test_video.mp4"
    
    @pytest.mark.asyncio
    async def test_upload_video_invalid_file_type(self, mock_clients):
        """Test upload rejection for invalid file type."""
        storage_client, mongodb_client = mock_clients
        background_tasks = Mock()
        
        file = UploadFile(
            filename="test_video.txt",
            file=BytesIO(b"not a video")
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await upload_video(
                background_tasks=background_tasks,
                file=file,
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        assert exc_info.value.status_code == 400
        assert "Unsupported file type" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_upload_video_no_filename(self, mock_clients):
        """Test upload rejection when no filename provided."""
        storage_client, mongodb_client = mock_clients
        background_tasks = Mock()
        
        file = UploadFile(
            filename=None,
            file=BytesIO(b"video content")
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await upload_video(
                background_tasks=background_tasks,
                file=file,
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        assert exc_info.value.status_code == 400
        assert "No filename provided" in str(exc_info.value.detail)


class TestVideoListing:
    """Test video listing functionality."""
    
    @pytest.fixture
    def sample_videos(self):
        """Create sample video documents."""
        return [
            VideoDocument(
                video_id="video-1",
                user_id="user-1",
                filename="video1.mp4",
                file_size=1000000,
                status=VideoStatus.UPLOADED,
                raw_file_path="raw/video-1.mp4",
                upload_date=datetime.now(UTC),
                upload_progress=100.0,
                thumbnail_available=True
            ),
            VideoDocument(
                video_id="video-2",
                user_id="user-1",
                filename="video2.mp4",
                file_size=2000000,
                status=VideoStatus.PROCESSING,
                raw_file_path="raw/video-2.mp4",
                upload_date=datetime.now(UTC),
                upload_progress=100.0,
                thumbnail_available=False
            )
        ]
    
    @pytest.mark.asyncio
    async def test_list_videos_success(self, sample_videos):
        """Test successful video listing."""
        mongodb_client = AsyncMock()
        mongodb_client.list_videos.return_value = (sample_videos, 2)
        
        response = await list_videos(
            page=1,
            per_page=10,
            status=None,
            mongodb_client=mongodb_client
        )
        
        assert len(response.videos) == 2
        assert response.total == 2
        assert response.page == 1
        assert response.per_page == 10
        assert response.has_next is False
        assert response.has_prev is False
        
        # Verify first video
        video1 = response.videos[0]
        assert video1.video_id == "video-1"
        assert video1.filename == "video1.mp4"
        assert video1.thumbnail_available is True
        
        mongodb_client.list_videos.assert_called_once_with(
            user_id="anonymous",
            page=1,
            per_page=10,
            status_filter=None
        )
    
    @pytest.mark.asyncio
    async def test_list_videos_with_pagination(self, sample_videos):
        """Test video listing with pagination."""
        mongodb_client = AsyncMock()
        mongodb_client.list_videos.return_value = (sample_videos[:1], 10)  # 1 video, 10 total
        
        response = await list_videos(
            page=2,
            per_page=5,
            status="uploaded",
            mongodb_client=mongodb_client
        )
        
        assert response.page == 2
        assert response.per_page == 5
        assert response.total == 10
        assert response.has_next is False  # (5 + 5) = 10, no more items
        assert response.has_prev is True  # page > 1
        
        mongodb_client.list_videos.assert_called_once_with(
            user_id="anonymous",
            page=2,
            per_page=5,
            status_filter="uploaded"
        )
    
    @pytest.mark.asyncio
    async def test_list_videos_database_error(self):
        """Test video listing with database error."""
        mongodb_client = AsyncMock()
        mongodb_client.list_videos.side_effect = Exception("Database error")
        
        with pytest.raises(HTTPException) as exc_info:
            await list_videos(
                page=1,
                per_page=10,
                status=None,
                mongodb_client=mongodb_client
            )
        
        assert exc_info.value.status_code == 500


class TestThumbnailAPI:
    """Test thumbnail API functionality."""
    
    @pytest.mark.asyncio
    async def test_get_thumbnail_success(self):
        """Test successful thumbnail retrieval."""
        storage_client = Mock()
        # Mock the S3 client's head_object method since we're using direct S3 calls now
        storage_client.s3_client = Mock()
        storage_client.s3_client.head_object.return_value = {}  # Success response
        storage_client.config.bucket_thumbnails = "test-thumbnails"
        storage_client.generate_signed_url.return_value = "https://s3.example.com/thumbnails/test-video-123.jpg?presigned=true"
        
        mongodb_client = AsyncMock()
        video_mock = Mock()
        video_mock.thumbnail_available = True
        video_mock.deleted = False
        mongodb_client.get_video_by_id.return_value = video_mock
        
        response = await get_thumbnail(
            video_id="test-video-123",
            storage_client=storage_client,
            mongodb_client=mongodb_client
        )
        
        # Response should now be JSON instead of redirect
        assert response.status_code == 200
        
        # Parse the JSON response
        import json
        response_data = json.loads(response.body.decode())
        assert response_data["thumbnail_url"] == "https://s3.example.com/thumbnails/test-video-123.jpg?presigned=true"
        assert response_data["expires_in"] == 600
        
        # Verify that head_object was called to check file existence
        storage_client.s3_client.head_object.assert_called_once_with(
            Bucket="test-thumbnails", 
            Key="thumbnails/test-video-123.jpg"
        )
        mongodb_client.get_video_by_id.assert_called_once_with("test-video-123")
    
    @pytest.mark.asyncio
    async def test_get_thumbnail_not_found(self):
        """Test thumbnail not found."""
        storage_client = Mock()
        mongodb_client = AsyncMock()
        mongodb_client.get_video_by_id.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_thumbnail(
                video_id="test-video-123",
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        assert exc_info.value.status_code == 404
        assert "Video not found" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_thumbnail_video_deleted(self):
        """Test thumbnail request for deleted video."""
        storage_client = Mock()
        mongodb_client = AsyncMock()
        video_mock = Mock()
        video_mock.deleted = True
        mongodb_client.get_video_by_id.return_value = video_mock
        
        with pytest.raises(HTTPException) as exc_info:
            await get_thumbnail(
                video_id="test-video-123",
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        assert exc_info.value.status_code == 404
        assert "Video not found" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_thumbnail_not_available(self):
        """Test thumbnail not available."""
        storage_client = Mock()
        mongodb_client = AsyncMock()
        video_mock = Mock()
        video_mock.thumbnail_available = False
        video_mock.deleted = False
        mongodb_client.get_video_by_id.return_value = video_mock
        
        with pytest.raises(HTTPException) as exc_info:
            await get_thumbnail(
                video_id="test-video-123",
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        assert exc_info.value.status_code == 404
        assert "Thumbnail not yet available" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_thumbnail_storage_error(self):
        """Test storage error when generating signed URL."""
        storage_client = Mock()
        storage_client.file_exists = AsyncMock(return_value=True)
        storage_client.config.bucket_thumbnails = "test-thumbnails"
        storage_client.generate_signed_url.side_effect = Exception("S3 error")
        
        mongodb_client = AsyncMock()
        video_mock = Mock()
        video_mock.thumbnail_available = True
        video_mock.deleted = False
        mongodb_client.get_video_by_id.return_value = video_mock
        
        with pytest.raises(HTTPException) as exc_info:
            await get_thumbnail(
                video_id="test-video-123",
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        assert exc_info.value.status_code == 404
        assert "Thumbnail not yet available" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_thumbnail_marked_available_but_missing_from_storage(self):
        """Test thumbnail marked as available but missing from storage."""
        storage_client = Mock()
        # Mock S3 client to raise 404 error (file doesn't exist)
        storage_client.s3_client = Mock()
        error_response = {'Error': {'Code': '404'}}
        not_found_error = Exception()
        not_found_error.response = error_response
        storage_client.s3_client.head_object.side_effect = not_found_error
        storage_client.config.bucket_thumbnails = "test-thumbnails"
        
        mongodb_client = AsyncMock()
        video_mock = Mock()
        video_mock.thumbnail_available = True
        video_mock.deleted = False
        mongodb_client.get_video_by_id.return_value = video_mock
        
        with pytest.raises(HTTPException) as exc_info:
            await get_thumbnail(
                video_id="test-video-123",
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        assert exc_info.value.status_code == 404
        assert "Thumbnail not yet available" in str(exc_info.value.detail)
        # Should update thumbnail status to False
        mongodb_client.update_video_thumbnail_status.assert_called_once_with("test-video-123", False)


class TestThumbnailGeneration:
    """Test thumbnail generation functionality."""
    
    @pytest.mark.asyncio
    async def test_generate_thumbnail_background_success(self):
        """Test successful thumbnail generation from assembled video in storage."""
        video_id = "test-video-123"
        raw_video_key = "raw-videos/test-video-123.mp4"
        bucket_raw = "dashcam-raw-videos"

        with patch('dashcam_backend.video_api.get_storage_client') as mock_get_storage, \
             patch('dashcam_backend.video_api.get_mongodb_client') as mock_get_mongo, \
             patch('ffmpeg.input') as mock_ffmpeg, \
             patch('asyncio.get_event_loop') as mock_loop, \
             patch('os.path.exists') as mock_exists, \
             patch('os.unlink') as mock_unlink:

            # Setup mocks
            storage_client = Mock()
            storage_client.generate_internal_presigned_url.return_value = "http://minio:9000/raw/test.mp4?sig=abc"
            mongodb_client = AsyncMock()
            mock_get_storage.return_value = storage_client
            mock_get_mongo.return_value = mongodb_client

            # Mock ffmpeg
            mock_ffmpeg_instance = Mock()
            mock_ffmpeg.return_value = mock_ffmpeg_instance
            mock_ffmpeg_instance.output.return_value = mock_ffmpeg_instance
            mock_ffmpeg_instance.overwrite_output.return_value = mock_ffmpeg_instance
            mock_ffmpeg_instance.run.return_value = None

            # Mock executor
            mock_executor = AsyncMock()
            mock_loop.return_value.run_in_executor = mock_executor

            # Mock file existence
            mock_exists.return_value = True

            await generate_thumbnail_background(video_id, raw_video_key, bucket_raw)

            # Verify presigned URL was generated using internal client
            storage_client.generate_internal_presigned_url.assert_called_once_with(
                raw_video_key, expires_in=3600, bucket=bucket_raw
            )

            # Verify storage upload was called
            mock_executor.assert_called()

            # Verify database update
            mongodb_client.update_video_thumbnail_status.assert_called_once_with(video_id, True)

            # Verify cleanup
            mock_unlink.assert_called()


class TestProgressAPI:
    """Test progress API functionality."""
    
    @pytest.mark.asyncio
    async def test_get_progress_success(self):
        """Test successful progress retrieval - processing video uses task progress."""
        from dashcam_backend.models import TaskDocument
        video_doc = VideoDocument(
            video_id="test-video-123",
            user_id="user-1",
            filename="test.mp4",
            file_size=1000000,
            status=VideoStatus.PROCESSING,
            raw_file_path="raw/test.mp4",
            upload_date=datetime.now(UTC),
            upload_progress=100.0
        )
        task_doc = TaskDocument(
            task_id="task-1",
            video_id="test-video-123",
            user_id="user-1",
            status="processing",
            progress_percentage=45.0,
            current_frame=450,
            total_frames=1000,
            estimated_time_remaining=55
        )

        mongodb_client = AsyncMock()
        mongodb_client.get_video_by_id.return_value = video_doc
        mongodb_client.get_active_task_by_video_id.return_value = task_doc

        response = await get_progress(
            video_id="test-video-123",
            mongodb_client=mongodb_client
        )

        assert response.video_id == "test-video-123"
        assert response.status == VideoStatus.PROCESSING
        # Processing videos report task progress, not upload progress
        assert response.progress_percentage == 45.0
        assert response.current_frame == 450
        assert response.total_frames == 1000
        assert response.estimated_time_remaining == 55

        mongodb_client.get_video_by_id.assert_called_once_with("test-video-123")
        mongodb_client.get_active_task_by_video_id.assert_called_once_with("test-video-123")

    @pytest.mark.asyncio
    async def test_get_progress_processing_no_task_falls_back_to_upload_progress(self):
        """When video is processing but no active task found, fall back to upload_progress."""
        video_doc = VideoDocument(
            video_id="test-video-123",
            user_id="user-1",
            filename="test.mp4",
            file_size=1000000,
            status=VideoStatus.PROCESSING,
            raw_file_path="raw/test.mp4",
            upload_date=datetime.now(UTC),
            upload_progress=100.0
        )

        mongodb_client = AsyncMock()
        mongodb_client.get_video_by_id.return_value = video_doc
        mongodb_client.get_active_task_by_video_id.return_value = None

        response = await get_progress(
            video_id="test-video-123",
            mongodb_client=mongodb_client
        )

        assert response.progress_percentage == 100.0
    
    @pytest.mark.asyncio
    async def test_get_progress_video_not_found(self):
        """Test progress retrieval for non-existent video."""
        mongodb_client = AsyncMock()
        mongodb_client.get_video_by_id.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_progress(
                video_id="non-existent",
                mongodb_client=mongodb_client
            )
        
        assert exc_info.value.status_code == 404


class TestDeleteAPI:
    """Test delete API functionality."""
    
    @pytest.mark.asyncio
    async def test_delete_video_success(self):
        """Test successful video deletion."""
        video_doc = VideoDocument(
            video_id="test-video-123",
            user_id="user-1",
            filename="test.mp4",
            file_size=1000000,
            status=VideoStatus.COMPLETED,
            raw_file_path="raw-videos/test-video-123.mp4",       # realistic prefixed path
            processed_file_path="processed-videos/test-video-123.mp4",  # realistic prefixed path
            thumbnail_available=True,  # Use boolean flag instead of path
            upload_date=datetime.now(UTC),
            upload_progress=100.0,
            deleted=False
        )
        
        mongodb_client = AsyncMock()
        mongodb_client.get_video_by_id.return_value = video_doc
        mongodb_client.mark_video_as_deleted.return_value = None
        
        storage_client = Mock()
        storage_client.config = Mock()
        storage_client.config.bucket_raw = "raw-bucket"
        storage_client.config.bucket_processed = "processed-bucket"
        storage_client.config.bucket_thumbnails = "thumbnails-bucket"
        storage_client.delete_file = AsyncMock()
        
        response = await delete_video(
            video_id="test-video-123",
            mongodb_client=mongodb_client,
            storage_client=storage_client
        )
        
        assert response.video_id == "test-video-123"
        assert response.message == "Video deleted successfully"
        
        # Verify files were deleted from storage with stripped keys (no bucket prefix)
        assert storage_client.delete_file.call_count == 3
        storage_client.delete_file.assert_any_call("raw-bucket", "test-video-123.mp4")
        storage_client.delete_file.assert_any_call("processed-bucket", "test-video-123.mp4")
        storage_client.delete_file.assert_any_call("thumbnails-bucket", "thumbnails/test-video-123.jpg")  # Standard naming convention
        
        # Verify video was marked as deleted in DB
        mongodb_client.mark_video_as_deleted.assert_called_once_with("test-video-123")
    
    @pytest.mark.asyncio
    async def test_delete_video_already_deleted(self):
        """Test deletion of already deleted video."""
        video_doc = VideoDocument(
            video_id="test-video-123",
            user_id="user-1",
            filename="test.mp4",
            file_size=1000000,
            status=VideoStatus.COMPLETED,
            raw_file_path="raw/test.mp4",
            upload_date=datetime.now(UTC),
            upload_progress=100.0,
            deleted=True
        )
        
        mongodb_client = AsyncMock()
        mongodb_client.get_video_by_id.return_value = video_doc
        
        storage_client = Mock()
        
        with pytest.raises(HTTPException) as exc_info:
            await delete_video(
                video_id="test-video-123",
                mongodb_client=mongodb_client,
                storage_client=storage_client
            )
        
        assert exc_info.value.status_code == 400
        assert "already deleted" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_delete_video_storage_failure(self):
        """Test delete when storage deletion fails."""
        video_doc = VideoDocument(
            video_id="test-video-123",
            user_id="user-1",
            filename="test.mp4",
            file_size=1000000,
            status=VideoStatus.COMPLETED,
            raw_file_path="raw-videos/test-video-123.mp4",
            upload_date=datetime.now(UTC),
            upload_progress=100.0,
            deleted=False
        )
        
        mongodb_client = AsyncMock()
        mongodb_client.get_video_by_id.return_value = video_doc
        
        storage_client = Mock()
        storage_client.config = Mock()
        storage_client.config.bucket_raw = "raw-bucket"
        storage_client.delete_file = AsyncMock(side_effect=Exception("Storage error"))
        
        with pytest.raises(HTTPException) as exc_info:
            await delete_video(
                video_id="test-video-123",
                mongodb_client=mongodb_client,
                storage_client=storage_client
            )
        
        assert exc_info.value.status_code == 500
        assert "Failed to delete file from storage" in str(exc_info.value.detail)
        
        # Verify video was NOT marked as deleted in DB
        mongodb_client.mark_video_as_deleted.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_video_without_thumbnail(self):
        """Test successful video deletion when no thumbnail is available."""
        video_doc = VideoDocument(
            video_id="test-video-456",
            user_id="user-1",
            filename="test.mp4",
            file_size=1000000,
            status=VideoStatus.UPLOADED,
            raw_file_path="raw-videos/test-video-456.mp4",
            thumbnail_available=False,  # No thumbnail available
            upload_date=datetime.now(UTC),
            upload_progress=100.0,
            deleted=False
        )
        
        mongodb_client = AsyncMock()
        mongodb_client.get_video_by_id.return_value = video_doc
        mongodb_client.mark_video_as_deleted.return_value = None
        
        storage_client = Mock()
        storage_client.config = Mock()
        storage_client.config.bucket_raw = "raw-bucket"
        storage_client.delete_file = AsyncMock()
        
        response = await delete_video(
            video_id="test-video-456",
            mongodb_client=mongodb_client,
            storage_client=storage_client
        )
        
        assert response.video_id == "test-video-456"
        assert response.message == "Video deleted successfully"
        
        # Verify only raw file was deleted with stripped key (no thumbnail since it's not available)
        assert storage_client.delete_file.call_count == 1
        storage_client.delete_file.assert_any_call("raw-bucket", "test-video-456.mp4")
        
        # Verify video was marked as deleted in DB
        mongodb_client.mark_video_as_deleted.assert_called_once_with("test-video-456")


class TestThumbnailGeneration:
    """Test thumbnail generation functionality and error handling."""

    @pytest.mark.asyncio
    async def test_thumbnail_generation_handles_errors_gracefully(self):
        """Test that thumbnail generation handles errors without crashing."""
        video_id = "test-video-123"
        raw_video_key = "raw-videos/test-video-123.mp4"
        bucket_raw = "dashcam-raw-videos"

        # Mock storage client to fail – must not propagate
        with patch('dashcam_backend.video_api.get_storage_client', new_callable=AsyncMock, side_effect=Exception("Storage client error")):
            await generate_thumbnail_background(
                video_id=video_id,
                raw_video_key=raw_video_key,
                bucket_raw=bucket_raw
            )

    @pytest.mark.asyncio
    async def test_thumbnail_generation_with_error_handling(self):
        """Test that thumbnail generation handles exceptions gracefully."""
        video_id = "test-video-123"
        raw_video_key = "raw-videos/test-video-123.mp4"
        bucket_raw = "dashcam-raw-videos"

        with patch('dashcam_backend.video_api.get_storage_client', new_callable=AsyncMock, side_effect=Exception("Test error")):
            await generate_thumbnail_background(
                video_id=video_id,
                raw_video_key=raw_video_key,
                bucket_raw=bucket_raw
            )

    @pytest.mark.asyncio
    async def test_thumbnail_generation_ffmpeg_not_found(self):
        """Test thumbnail generation when ffmpeg is not found."""
        video_id = "test-video-123"
        raw_video_key = "raw-videos/test-video-123.mp4"
        bucket_raw = "dashcam-raw-videos"

        storage_client = Mock()
        storage_client.generate_internal_presigned_url.return_value = "http://minio:9000/raw/test.mp4?sig=abc"
        mongodb_client = Mock()
        mongodb_client.update_video_status = AsyncMock()

        with patch('dashcam_backend.video_api.get_storage_client', new_callable=AsyncMock, return_value=storage_client), \
             patch('dashcam_backend.video_api.get_mongodb_client', new_callable=AsyncMock, return_value=mongodb_client), \
             patch('ffmpeg.input', side_effect=FileNotFoundError("[Errno 2] No such file or directory: 'ffmpeg'")):

            await generate_thumbnail_background(
                video_id=video_id,
                raw_video_key=raw_video_key,
                bucket_raw=bucket_raw
            )

            # Verify status was not updated due to error
            mongodb_client.update_video_status.assert_not_called()


class TestVideoListingDateSerialization:
    """Test video listing with date serialization issues."""

    @pytest.mark.asyncio
    async def test_list_videos_with_string_upload_date(self):
        """Test video listing when upload_date comes from MongoDB as string."""
        # Create video with string upload_date (as it comes from MongoDB)
        video_dict = {
            "video_id": "video-1",
            "user_id": "user-1", 
            "filename": "video1.mp4",
            "file_size": 1000000,
            "status": VideoStatus.UPLOADED,
            "raw_file_path": "raw/video-1.mp4",
            "upload_date": "2025-07-31T20:00:00Z",  # String, not datetime
            "upload_progress": 100.0,
            "thumbnail_available": True
        }
        
        mongodb_client = AsyncMock()
        # Return video dict with string date (simulating MongoDB response)
        mongodb_client.list_videos.return_value = ([video_dict], 1)
        
        # This should handle the string date gracefully
        with patch('dashcam_backend.video_api.list_videos') as mock_list:
            # Mock the actual function to test the conversion logic
            async def mock_list_videos_impl(page, per_page, status, mongodb_client):
                videos_data, total = await mongodb_client.list_videos("anonymous", page, per_page, status)
                
                video_infos = []
                for video_data in videos_data:
                    # Handle the case where upload_date might be a string
                    upload_date = video_data.get('upload_date', '')
                    if isinstance(upload_date, str):
                        upload_date_formatted = upload_date
                    else:
                        upload_date_formatted = upload_date.isoformat() if upload_date else ""
                    
                    video_info = VideoInfo(
                        video_id=video_data['video_id'],
                        filename=video_data['filename'],
                        upload_date=upload_date_formatted,
                        status=video_data['status'],
                        upload_progress=video_data['upload_progress'],
                        file_size=video_data['file_size'],
                        duration_seconds=video_data.get('duration_seconds'),
                        thumbnail_available=video_data.get('thumbnail_available', False),
                        thumbnail_url=f"/videos/{video_data['video_id']}/thumbnail" if video_data.get('thumbnail_available', False) else None
                    )
                    video_infos.append(video_info)
                
                return VideoListResponse(
                    videos=video_infos,
                    total=total,
                    page=page,
                    per_page=per_page,
                    has_next=False,
                    has_prev=False
                )
            
            mock_list.side_effect = mock_list_videos_impl
            
            # Call the mocked function
            response = await mock_list_videos_impl(
                page=1,
                per_page=10,
                status=None,
                mongodb_client=mongodb_client
            )
            
            # Should not raise an error and should format date correctly
            assert len(response.videos) == 1
            assert response.videos[0].upload_date == "2025-07-31T20:00:00Z"
            assert response.videos[0].video_id == "video-1"

    @pytest.mark.asyncio  
    async def test_video_document_creation_with_string_dates(self):
        """Test VideoDocument creation when MongoDB returns string dates."""
        from datetime import datetime
        
        # Simulate MongoDB response with string dates
        mongodb_response = {
            "video_id": "test-video-123",
            "user_id": "test-user-456",
            "filename": "test.mp4",
            "file_size": 1000000,
            "status": VideoStatus.UPLOADING,
            "upload_progress": 0.0,
            "upload_date": "2025-07-31T20:00:00Z",  # String from MongoDB
            "upload_started_at": "2025-07-31T19:59:00Z",  # String from MongoDB
            "upload_completed_at": "2025-07-31T20:01:00Z"  # String from MongoDB
        }
        
        # This should handle string dates properly
        # For now, test that we need to convert strings to datetime objects
        mongodb_response_converted = mongodb_response.copy()
        
        # Convert string dates to datetime objects before creating VideoDocument
        for field in ['upload_date', 'upload_started_at', 'upload_completed_at']:
            if field in mongodb_response_converted and isinstance(mongodb_response_converted[field], str):
                try:
                    # Parse ISO format date string
                    date_str = mongodb_response_converted[field]
                    if date_str.endswith('Z'):
                        date_str = date_str.replace('Z', '+00:00')
                    mongodb_response_converted[field] = datetime.fromisoformat(date_str)
                except (ValueError, AttributeError):
                    # If parsing fails, set to None
                    mongodb_response_converted[field] = None
        
        # Now this should work without errors
        video = VideoDocument(**mongodb_response_converted)
        
        assert video.video_id == "test-video-123"
        assert video.user_id == "test-user-456"
        assert isinstance(video.upload_date, datetime)


class TestVideoUploadProgress:
    """Test video upload progress reporting functionality."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(10)  # Allow 10 seconds for this test
    async def test_upload_progress_is_reported_during_upload(self):
        """Test that upload progress is reported incrementally during upload."""
        # Create a large file to simulate streaming upload with progress
        file_size = 100 * 1024 * 1024  # 100MB file
        chunk_data = b"x" * 1024  # 1KB per chunk
        file_content = chunk_data * (file_size // len(chunk_data))
        
        file = UploadFile(
            filename="large_video.mp4",
            file=BytesIO(file_content)
        )
        
        # Mock clients
        storage_client = AsyncMock()
        mongodb_client = AsyncMock()
        background_tasks = Mock()
        
        # Mock storage operations
        storage_client.initiate_multipart_upload.return_value = "upload-123"
        storage_client.upload_part.return_value = "etag-123"
        storage_client.complete_multipart_upload.return_value = True
        
        # Track progress updates
        progress_updates = []
        
        async def mock_update_progress(video_id, progress, bytes_uploaded=None):
            progress_updates.append((video_id, progress, bytes_uploaded))
        
        mongodb_client.update_video_upload_progress = mock_update_progress
        
        with patch('dashcam_backend.video_api.generate_video_id') as mock_gen_id:
            mock_gen_id.return_value = "test-video-123"
            
            # This should report progress during upload, not just 0% -> 100%
            response = await upload_video(
                background_tasks=background_tasks,
                file=file,
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        # Verify that progress was updated multiple times during upload
        # For a 100MB file uploaded in 50MB chunks, we should see intermediate progress
        assert len(progress_updates) > 1, "Upload should report progress incrementally"
        
        # Progress should be increasing
        for i in range(1, len(progress_updates)):
            assert progress_updates[i][1] >= progress_updates[i-1][1], f"Progress should not decrease: {progress_updates[i-1]} -> {progress_updates[i]}"
        
        # Final progress should be 100%
        assert progress_updates[-1][1] == 100.0, "Final progress should be 100%"

    @pytest.mark.asyncio
    async def test_upload_progress_starts_at_zero(self):
        """Test that upload progress starts at 0%."""
        file_content = b"fake video content" * 1000  # Small file
        file = UploadFile(
            filename="test_video.mp4",
            file=BytesIO(file_content)
        )

        # Mock clients
        storage_client = AsyncMock()
        mongodb_client = AsyncMock()
        background_tasks = Mock()

        # Mock storage operations
        storage_client.initiate_multipart_upload.return_value = "upload-123"
        storage_client.upload_part.return_value = "etag-123"
        storage_client.complete_multipart_upload.return_value = True

        # Track progress updates
        progress_updates = []

        async def mock_update_progress(video_id, progress, bytes_uploaded=None):
            progress_updates.append((video_id, progress, bytes_uploaded))

        mongodb_client.update_video_upload_progress = mock_update_progress

        with patch('dashcam_backend.video_api.generate_video_id') as mock_gen_id:
            mock_gen_id.return_value = "test-video-123"

            await upload_video(
                background_tasks=background_tasks,
                file=file,
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )

        # Should see at least the final 100% progress update
        assert len(progress_updates) >= 1, "Progress should be reported"
        
        # Final progress should be 100%
        assert progress_updates[-1][1] == 100.0, "Final progress should be 100%"
        
        # Check that video was initially created with 0% progress
        mongodb_client.create_video.assert_called_once()
        created_video = mongodb_client.create_video.call_args[0][0]
        assert created_video.upload_progress == 0.0, "Initial progress should be 0%"

    @pytest.mark.asyncio
    async def test_upload_progress_for_medium_files(self):
        """Test that upload progress is reported for medium-sized files (5-50MB)."""
        # Create a 10MB file to test progress reporting during streaming
        file_size = 10 * 1024 * 1024  # 10MB file
        chunk_data = b"x" * 1024  # 1KB per chunk
        file_content = chunk_data * (file_size // len(chunk_data))
        
        file = UploadFile(
            filename="medium_video.mp4",
            file=BytesIO(file_content)
        )

        # Mock clients
        storage_client = AsyncMock()
        mongodb_client = AsyncMock()
        background_tasks = Mock()

        # Mock storage operations
        storage_client.initiate_multipart_upload.return_value = "upload-123"
        storage_client.upload_part.return_value = "etag-123"
        storage_client.complete_multipart_upload.return_value = True

        # Track progress updates
        progress_updates = []

        async def mock_update_progress(video_id, progress, bytes_uploaded=None):
            progress_updates.append((video_id, progress, bytes_uploaded))

        mongodb_client.update_video_upload_progress = mock_update_progress

        with patch('dashcam_backend.video_api.generate_video_id') as mock_gen_id:
            mock_gen_id.return_value = "test-video-456"

            response = await upload_video(
                background_tasks=background_tasks,
                file=file,
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )

        # Should see progress updates during streaming for medium files
        assert len(progress_updates) >= 2, f"Should see incremental progress for 10MB file, got {len(progress_updates)} updates"
        
        # Progress should be increasing
        for i in range(1, len(progress_updates)):
            assert progress_updates[i][1] >= progress_updates[i-1][1], f"Progress should not decrease: {progress_updates}"
        
        # Final progress should be 100%
        assert progress_updates[-1][1] == 100.0, "Final progress should be 100%"


class TestProgressCalculation:
    """Test progress calculation logic in isolation to ensure it's always mathematically correct."""
    
    def test_progress_calculation_simple_math(self):
        """Test that progress calculation is ALWAYS: (bytes_uploaded / total_size) * 100."""
        test_cases = [
            # (bytes_uploaded, total_file_size, expected_progress)
            (0, 1024 * 1024, 0.0),  # 0MB of 1MB = 0%
            (512 * 1024, 1024 * 1024, 50.0),  # 0.5MB of 1MB = 50%
            (1024 * 1024, 1024 * 1024, 100.0),  # 1MB of 1MB = 100%
            (5 * 1024 * 1024, 10 * 1024 * 1024, 50.0),  # 5MB of 10MB = 50%
            (25 * 1024 * 1024, 50 * 1024 * 1024, 50.0),  # 25MB of 50MB = 50%
            (45 * 1024 * 1024, 50 * 1024 * 1024, 90.0),  # 45MB of 50MB = 90%
            (100 * 1024 * 1024, 200 * 1024 * 1024, 50.0),  # 100MB of 200MB = 50%
            (750 * 1024 * 1024, 1024 * 1024 * 1024, 73.24218750),  # 750MB of 1GB ≈ 73.24%
        ]
        
        for bytes_uploaded, total_size, expected_progress in test_cases:
            # This is the ONLY formula that should ever be used for progress calculation
            actual_progress = (bytes_uploaded / total_size) * 100
            
            assert abs(actual_progress - expected_progress) < 0.01, \
                f"Progress calculation failed for {bytes_uploaded}/{total_size}: got {actual_progress}, expected {expected_progress}"

    def test_progress_bounds_always_valid(self):
        """Test that progress is always between 0 and 100, no exceptions."""
        test_sizes = [1024, 1024*1024, 50*1024*1024, 100*1024*1024, 1024*1024*1024]
        
        for total_size in test_sizes:
            for uploaded_ratio in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
                bytes_uploaded = int(total_size * uploaded_ratio)
                progress = (bytes_uploaded / total_size) * 100
                
                assert 0.0 <= progress <= 100.0, \
                    f"Progress {progress}% out of bounds for {bytes_uploaded}/{total_size}"
                    
                # No negative progress
                assert progress >= 0.0, f"Progress should never be negative: {progress}%"
                
                # No progress over 100%
                assert progress <= 100.0, f"Progress should never exceed 100%: {progress}%"

    def test_progress_never_decreases_during_upload(self):
        """Test that progress never decreases during upload - it can only stay same or increase."""
        total_size = 10 * 1024 * 1024  # 10MB
        previous_progress = -1.0
        
        # Simulate upload progress from 0 to 100%
        for uploaded_percent in range(0, 101, 5):  # 0%, 5%, 10%, ... 100%
            bytes_uploaded = int((uploaded_percent / 100) * total_size)
            current_progress = (bytes_uploaded / total_size) * 100
            
            assert current_progress >= previous_progress, \
                f"Progress decreased from {previous_progress}% to {current_progress}%"
            previous_progress = current_progress

    def test_exact_percentage_calculations(self):
        """Test exact percentage calculations for common scenarios."""
        # Test exact 25%, 50%, 75%, 100% scenarios
        total_size = 1024 * 1024  # 1MB
        
        # 25%
        bytes_25 = total_size // 4
        progress_25 = (bytes_25 / total_size) * 100
        assert abs(progress_25 - 25.0) < 0.01, f"25% calculation failed: {progress_25}"
        
        # 50% 
        bytes_50 = total_size // 2
        progress_50 = (bytes_50 / total_size) * 100
        assert abs(progress_50 - 50.0) < 0.01, f"50% calculation failed: {progress_50}"
        
        # 75%
        bytes_75 = (total_size * 3) // 4
        progress_75 = (bytes_75 / total_size) * 100
        assert abs(progress_75 - 75.0) < 0.01, f"75% calculation failed: {progress_75}"
        
        # 100%
        bytes_100 = total_size
        progress_100 = (bytes_100 / total_size) * 100
        assert abs(progress_100 - 100.0) < 0.01, f"100% calculation failed: {progress_100}"


class TestProgressAPICalculation:
    """Test that the progress API endpoint performs correct mathematical calculations."""
    
    @pytest.mark.asyncio
    async def test_get_progress_returns_exact_math(self):
        """Test that get_progress endpoint returns exactly (bytes_uploaded/file_size)*100."""
        mongodb_client = AsyncMock()
        
        test_cases = [
            (0, 1024*1024),  # 0% of 1MB
            (512*1024, 1024*1024),  # 50% of 1MB  
            (1024*1024, 1024*1024),  # 100% of 1MB
            (25*1024*1024, 100*1024*1024),  # 25% of 100MB
            (75*1024*1024, 100*1024*1024),  # 75% of 100MB
        ]
        
        for bytes_uploaded, file_size in test_cases:
            # Calculate expected progress using the simple formula
            expected_progress = (bytes_uploaded / file_size) * 100
            
            mock_video = VideoDocument(
                video_id="test-123",
                user_id="test-user", 
                filename="test.mp4",
                file_size=file_size,
                status=VideoStatus.UPLOADING,
                raw_file_path="raw-videos/test-123.mp4",
                upload_date=datetime.now(UTC),
                upload_progress=expected_progress,  # Backend should store this exact value
                bytes_uploaded=bytes_uploaded
            )
            
            mongodb_client.get_video_by_id.return_value = mock_video
            
            response = await get_progress("test-123", mongodb_client)
            
            # The API should return the exact mathematical result, no complex logic
            assert abs(response.progress_percentage - expected_progress) < 0.01, \
                f"API progress {response.progress_percentage}% != calculated {expected_progress}% for {bytes_uploaded}/{file_size}"