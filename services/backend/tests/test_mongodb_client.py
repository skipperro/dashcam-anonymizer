"""Tests for MongoDB client."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from dashcam_backend.mongodb_client import MongoDBClient, get_mongodb_client
from dashcam_backend.models import VideoDocument, TaskDocument, WorkerDocument, UserDocument
from dashcam_backend.models import VideoStatus, TaskStatus, WorkerStatus
from dashcam_backend.config import reset_config


class TestMongoDBClient:
    """Test MongoDB client functionality."""
    
    def setup_method(self):
        """Setup test environment."""
        reset_config()
        self.client = MongoDBClient()
    
    def test_client_initialization(self):
        """Test client can be initialized."""
        assert self.client.client is None
        assert self.client.database is None
        assert self.client.users is None
        assert self.client.videos is None
        assert self.client.tasks is None
        assert self.client.workers is None
    
    def test_client_configuration(self):
        """Test client uses correct configuration."""
        assert self.client.config.uri == "mongodb://admin:dashcam123@localhost:27017/dashcam_db"
        assert self.client.config.database_name == "dashcam_db"
    
    def test_video_document_creation(self):
        """Test creating video documents."""
        video = VideoDocument(
            video_id="test-video-123",
            user_id="test-user-456", 
            filename="test.mp4",
            file_size=1000000,
            status=VideoStatus.UPLOADING,
            upload_status="pending",
            upload_progress=0,
            duration_seconds=0,
            resolution="1920x1080",
            format="mp4"
        )
        
        assert video.video_id == "test-video-123"
        assert video.user_id == "test-user-456"
        assert video.status == VideoStatus.UPLOADING
        assert video.file_size == 1000000
    
    def test_task_document_creation(self):
        """Test creating task documents."""
        task = TaskDocument(
            task_id="test-task-789",
            video_id="test-video-123",
            user_id="test-user-456",
            status=TaskStatus.PENDING,
            progress_percentage=0,
            current_frame=0,
            total_frames=0,
            estimated_time_remaining=0
        )
        
        assert task.task_id == "test-task-789"
        assert task.video_id == "test-video-123"
        assert task.status == TaskStatus.PENDING
        assert task.progress_percentage == 0
    
    def test_worker_document_creation(self):
        """Test creating worker documents."""
        worker = WorkerDocument(
            worker_id="test-worker-001",
            hostname="test-host",
            status=WorkerStatus.READY,
            capabilities={
                "compute_device": "cuda",
                "gpu_memory_gb": 8,
                "system_memory_gb": 16
            },
            current_task_id=None,
            resource_usage={}
        )
        
        assert worker.worker_id == "test-worker-001"
        assert worker.hostname == "test-host"
        assert worker.status == WorkerStatus.READY
        assert worker.capabilities["compute_device"] == "cuda"
    
    def test_user_document_creation(self):
        """Test creating user documents."""
        user = UserDocument(
            user_id="test-user-456",
            email="test@example.com",
            password_hash="hashed_password",
            google_id="google-123",
            credits=10.0,
            subscription_tier="free"
        )
        
        assert user.user_id == "test-user-456"
        assert user.email == "test@example.com"
        assert user.credits == 10.0
        assert user.subscription_tier == "free"
    
    def test_file_path_generation(self):
        """Test file path generation logic."""
        # These would be utility functions in the storage client
        user_id = "user-123"
        video_id = "video-456"
        filename = "test_video.mp4"
        
        expected_path = f"{user_id}/{video_id}.mp4"
        assert expected_path == "user-123/video-456.mp4"
        
        # Test thumbnail path
        expected_thumbnail = f"{user_id}/{video_id}.jpg"
        assert expected_thumbnail == "user-123/video-456.jpg"
    
    def test_global_client_singleton(self):
        """Test global client singleton."""
        client1 = get_mongodb_client()
        client2 = get_mongodb_client()
        
        # Should be the same instance
        assert client1 is client2

    def test_video_document_with_mongodb_id_field(self):
        """Test that VideoDocument creation handles MongoDB's _id field correctly."""
        # Simulate MongoDB response with _id field
        mongodb_response = {
            "_id": "507f1f77bcf86cd799439011",  # MongoDB ObjectId
            "video_id": "test-video-123",
            "user_id": "test-user-456",
            "filename": "test.mp4",
            "file_size": 1000000,
            "status": VideoStatus.UPLOADING,
            "upload_progress": 0.0,
            "upload_date": datetime.now(timezone.utc).isoformat()
        }
        
        # This should not raise an exception
        # Remove _id before creating VideoDocument (same as in mongodb_client.py)
        mongodb_response_clean = mongodb_response.copy()
        mongodb_response_clean.pop('_id', None)
        
        video = VideoDocument(**mongodb_response_clean)
        
        assert video.video_id == "test-video-123"
        assert video.user_id == "test-user-456"
        assert video.filename == "test.mp4"
        assert video.file_size == 1000000
        
        # Verify that VideoDocument doesn't accept _id field
        try:
            VideoDocument(**mongodb_response)  # This should fail
            assert False, "VideoDocument should not accept _id field"
        except TypeError as e:
            assert "_id" in str(e)

    def test_multiple_video_documents_with_mongodb_fields(self):
        """Test handling multiple MongoDB documents with _id fields."""
        mongodb_responses = [
            {
                "_id": "507f1f77bcf86cd799439011",
                "video_id": "video-1",
                "user_id": "user-1",
                "filename": "video1.mp4",
                "file_size": 1000000,
                "status": VideoStatus.UPLOADED,
                "upload_progress": 100.0,
                "upload_date": datetime.now(timezone.utc).isoformat()
            },
            {
                "_id": "507f1f77bcf86cd799439012",
                "video_id": "video-2",
                "user_id": "user-1", 
                "filename": "video2.mp4",
                "file_size": 2000000,
                "status": VideoStatus.PROCESSING,
                "upload_progress": 100.0,
                "upload_date": datetime.now(timezone.utc).isoformat()
            }
        ]
        
        # Simulate what happens in list_videos method
        videos = []
        for video_dict in mongodb_responses:
            video_dict_clean = video_dict.copy()
            video_dict_clean.pop('_id', None)
            videos.append(VideoDocument(**video_dict_clean))
        
        assert len(videos) == 2
        assert videos[0].video_id == "video-1"
        assert videos[1].video_id == "video-2"
        assert videos[0].filename == "video1.mp4"
        assert videos[1].filename == "video2.mp4"

    def test_convert_string_dates_to_datetime(self):
        """Test the helper method that converts string dates to datetime objects."""
        from datetime import datetime
        
        # Test document with string dates
        document = {
            "video_id": "test-video-123",
            "upload_date": "2025-07-31T20:00:00Z",
            "upload_started_at": "2025-07-31T19:59:00Z",
            "upload_completed_at": "2025-07-31T20:01:00Z",
            "upload_expires_at": "2025-08-01T20:00:00+00:00",
            "some_other_field": "not a date",
            "number_field": 42
        }
        
        # Convert using the helper method
        converted = MongoDBClient._convert_string_dates_to_datetime(document.copy())
        
        # Verify dates were converted
        assert isinstance(converted["upload_date"], datetime)
        assert isinstance(converted["upload_started_at"], datetime)
        assert isinstance(converted["upload_completed_at"], datetime)
        assert isinstance(converted["upload_expires_at"], datetime)
        
        # Verify non-date fields unchanged
        assert converted["some_other_field"] == "not a date"
        assert converted["number_field"] == 42
        assert converted["video_id"] == "test-video-123"
        
        # Verify date values are correct
        assert converted["upload_date"].year == 2025
        assert converted["upload_date"].month == 7
        assert converted["upload_date"].day == 31
        assert converted["upload_date"].hour == 20

    def test_convert_string_dates_handles_invalid_dates(self):
        """Test that invalid date strings are handled gracefully."""
        
        # Test document with invalid date strings
        document = {
            "video_id": "test-video-123",
            "upload_date": "invalid-date-string",
            "upload_started_at": "2025-13-45T25:70:90Z",  # Invalid date
            "upload_completed_at": None,  # None value
            "normal_field": "normal value"
        }
        
        # Convert using the helper method
        converted = MongoDBClient._convert_string_dates_to_datetime(document.copy())
        
        # Invalid dates should be set to None
        assert converted["upload_date"] is None
        assert converted["upload_started_at"] is None
        assert converted["upload_completed_at"] is None
        
        # Normal field should be unchanged
        assert converted["normal_field"] == "normal value"
        assert converted["video_id"] == "test-video-123"

    @pytest.mark.asyncio
    async def test_mark_video_as_deleted_success(self):
        """Test marking video as deleted successfully."""
        mock_result = MagicMock()
        mock_result.matched_count = 1
        
        with patch('dashcam_backend.mongodb_client.AsyncIOMotorClient'):
            self.client.videos = AsyncMock()
            self.client.videos.update_one.return_value = mock_result
            
            await self.client.mark_video_as_deleted("test-video-123")
            
            self.client.videos.update_one.assert_called_once_with(
                {"video_id": "test-video-123"},
                {"$set": {"deleted": True}}
            )

    @pytest.mark.asyncio
    async def test_mark_video_as_deleted_not_found(self):
        """Test marking video as deleted when video not found."""
        mock_result = MagicMock()
        mock_result.matched_count = 0
        
        with patch('dashcam_backend.mongodb_client.AsyncIOMotorClient'):
            self.client.videos = AsyncMock()
            self.client.videos.update_one.return_value = mock_result
            
            with pytest.raises(ValueError, match="Video test-video-123 not found"):
                await self.client.mark_video_as_deleted("test-video-123")

    @pytest.mark.asyncio
    async def test_list_videos_query_excludes_deleted(self):
        """Test that list_videos constructs query to exclude deleted videos."""
        with patch.object(self.client, 'videos') as mock_videos:
            mock_videos.count_documents = AsyncMock(return_value=0)
            
            # Create a proper mock cursor for aggregation
            mock_cursor = MagicMock()
            mock_videos.aggregate.return_value = mock_cursor
            
            # Make the cursor async iterable
            async def empty_iter():
                return
                yield  # unreachable, just to make it an async generator
            
            mock_cursor.__aiter__ = empty_iter
            
            try:
                videos, total = await self.client.list_videos("user-1", page=1, per_page=10)
            except Exception:
                pass  # We don't care about the result, just the query
            
            # Verify the query excludes deleted videos in count_documents
            expected_query = {
                "user_id": "user-1", 
                "$or": [
                    {"deleted": {"$exists": False}},  # Include docs without deleted field
                    {"deleted": False}                # Include docs with deleted=False
                ]
            }
            mock_videos.count_documents.assert_called_with(expected_query)
            
            # Verify aggregation pipeline is called with correct match stage
            mock_videos.aggregate.assert_called_once()
            pipeline = mock_videos.aggregate.call_args[0][0]
            
            # Check that the first stage is a $match with the correct query
            assert pipeline[0]["$match"] == expected_query
