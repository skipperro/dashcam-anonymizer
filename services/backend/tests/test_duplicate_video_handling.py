"""Test duplicate video handling and retry logic."""

import pytest
from unittest.mock import AsyncMock, Mock
from io import BytesIO
from fastapi import UploadFile

from dashcam_backend.video_api import upload_video
from dashcam_backend.models import VideoDocument


class TestDuplicateVideoHandling:
    """Test handling of duplicate video IDs and retry logic."""

    @pytest.mark.asyncio
    async def test_duplicate_video_id_retry_success(self):
        """Test that duplicate video ID is handled with retry logic."""
        # Create file mock
        file_content = b"fake video content" * 1000
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

        # Mock create_video to fail first time, succeed second time
        call_count = 0
        
        async def mock_create_video(video_doc):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call fails with duplicate error
                raise ValueError("Video already exists")
            else:
                # Second call succeeds
                return "mongo-object-id"
        
        mongodb_client.create_video = mock_create_video

        # Mock update methods
        mongodb_client.update_video_upload_progress = AsyncMock()
        mongodb_client.update_video_status = AsyncMock()
        mongodb_client.videos.update_one = AsyncMock()

        # Call upload_video
        response = await upload_video(
            background_tasks=background_tasks,
            file=file,
            storage_client=storage_client,
            mongodb_client=mongodb_client
        )

        # Verify retry logic worked
        assert call_count == 2, "create_video should have been called twice (retry)"
        assert response.status == "uploaded"
        assert response.video_id is not None

    @pytest.mark.asyncio
    async def test_duplicate_video_id_max_retries_exceeded(self):
        """Test that max retries are respected when duplicates persist."""
        # Create file mock
        file_content = b"fake video content" * 1000
        file = UploadFile(
            filename="test_video.mp4",
            file=BytesIO(file_content)
        )

        # Mock clients
        storage_client = AsyncMock()
        mongodb_client = AsyncMock()
        background_tasks = Mock()

        # Mock create_video to always fail
        async def mock_create_video_always_fail(video_doc):
            raise ValueError("Video already exists")
        
        mongodb_client.create_video = mock_create_video_always_fail

        # Call should raise HTTPException after max retries
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await upload_video(
                background_tasks=background_tasks,
                file=file,
                storage_client=storage_client,
                mongodb_client=mongodb_client
            )
        
        assert exc_info.value.status_code == 500
        assert "Failed to create video" in str(exc_info.value.detail)
