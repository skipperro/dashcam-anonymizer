"""Storage client for S3-compatible operations."""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

from .config import get_config
from .logging import get_logger


logger = get_logger(__name__)


class StorageClient:
    """S3-compatible storage client for file operations."""
    
    def __init__(self):
        self.config = get_config().storage
        self.s3_client = None
        self.s3_client_public = None  # For pre-signed URLs accessible from browser
        self._setup_client()
    
    def _setup_client(self) -> None:
        """Initialize S3 client with configuration."""
        try:
            # Configure boto3 client
            config = Config(
                retries={'max_attempts': 3, 'mode': 'adaptive'},
                max_pool_connections=50
            )
            
            # Create S3 client for internal operations (container-to-container)
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.config.endpoint if self.config.storage_type == 'minio' else None,
                aws_access_key_id=self.config.access_key,
                aws_secret_access_key=self.config.secret_key,
                region_name='us-east-1',  # Required for MinIO compatibility
                config=config
            )
            
            # Create S3 client for public URL generation (browser-accessible)
            self.s3_client_public = boto3.client(
                's3',
                endpoint_url=self.config.endpoint_public if self.config.storage_type == 'minio' else None,
                aws_access_key_id=self.config.access_key,
                aws_secret_access_key=self.config.secret_key,
                region_name='us-east-1',  # Required for MinIO compatibility
                config=config
            )
            
            logger.info(
                "Initialized storage client",
                storage_type=self.config.storage_type,
                endpoint=self.config.endpoint,
                endpoint_public=self.config.endpoint_public
            )
            
        except Exception as e:
            logger.error("Failed to initialize storage client", error=str(e))
            raise
    
    async def ensure_buckets_exist(self) -> None:
        """Ensure all required buckets exist."""
        buckets = [
            self.config.bucket_raw,
            self.config.bucket_processed,
            self.config.bucket_thumbnails,
            self.config.bucket_temp
        ]
        
        for bucket in buckets:
            await self._ensure_bucket_exists(bucket)
    
    async def _ensure_bucket_exists(self, bucket_name: str) -> None:
        """Ensure a specific bucket exists."""
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            
            def check_bucket():
                try:
                    self.s3_client.head_bucket(Bucket=bucket_name)
                    return True
                except ClientError as e:
                    error_code = int(e.response['Error']['Code'])
                    if error_code == 404:
                        return False
                    raise
            
            exists = await loop.run_in_executor(None, check_bucket)
            
            if not exists:
                def create_bucket():
                    self.s3_client.create_bucket(Bucket=bucket_name)
                
                await loop.run_in_executor(None, create_bucket)
                logger.info("Created bucket", bucket=bucket_name)
            else:
                logger.debug("Bucket exists", bucket=bucket_name)
                
        except Exception as e:
            logger.error("Failed to ensure bucket exists", bucket=bucket_name, error=str(e))
            raise
    
    async def generate_signed_upload_url(
        self,
        bucket: str,
        key: str,
        expires_in: int = 3600
    ) -> str:
        """Generate a signed URL for file upload."""
        try:
            loop = asyncio.get_event_loop()
            
            def generate_url():
                return self.s3_client.generate_presigned_url(
                    'put_object',
                    Params={'Bucket': bucket, 'Key': key},
                    ExpiresIn=expires_in
                )
            
            url = await loop.run_in_executor(None, generate_url)
            
            logger.debug(
                "Generated signed upload URL",
                bucket=bucket,
                key=key,
                expires_in=expires_in
            )
            
            return url
            
        except Exception as e:
            logger.error("Failed to generate signed upload URL", bucket=bucket, key=key, error=str(e))
            raise
    
    async def generate_signed_download_url(
        self,
        bucket: str,
        key: str,
        expires_in: int = 3600
    ) -> str:
        """Generate a signed URL for file download."""
        try:
            loop = asyncio.get_event_loop()
            
            def generate_url():
                return self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': bucket, 'Key': key},
                    ExpiresIn=expires_in
                )
            
            url = await loop.run_in_executor(None, generate_url)
            
            logger.debug(
                "Generated signed download URL",
                bucket=bucket,
                key=key,
                expires_in=expires_in
            )
            
            return url
            
        except Exception as e:
            logger.error("Failed to generate signed download URL", bucket=bucket, key=key, error=str(e))
            raise
    
    async def move_file(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
        delete_source: bool = True
    ) -> None:
        """Move a file from one location to another."""
        try:
            loop = asyncio.get_event_loop()
            
            def copy_file():
                copy_source = {'Bucket': source_bucket, 'Key': source_key}
                self.s3_client.copy(copy_source, dest_bucket, dest_key)
            
            def delete_file():
                self.s3_client.delete_object(Bucket=source_bucket, Key=source_key)
            
            # Copy file
            await loop.run_in_executor(None, copy_file)
            
            # Delete source if requested
            if delete_source:
                await loop.run_in_executor(None, delete_file)
            
            logger.info(
                "Moved file",
                source_bucket=source_bucket,
                source_key=source_key,
                dest_bucket=dest_bucket,
                dest_key=dest_key,
                delete_source=delete_source
            )
            
        except Exception as e:
            logger.error(
                "Failed to move file",
                source_bucket=source_bucket,
                source_key=source_key,
                dest_bucket=dest_bucket,
                dest_key=dest_key,
                error=str(e)
            )
            raise
    
    async def file_exists(self, bucket: str, key: str) -> bool:
        """Check if a file exists in storage."""
        try:
            loop = asyncio.get_event_loop()
            
            def check_file():
                try:
                    self.s3_client.head_object(Bucket=bucket, Key=key)
                    return True
                except ClientError as e:
                    if int(e.response['Error']['Code']) == 404:
                        return False
                    raise
            
            exists = await loop.run_in_executor(None, check_file)
            return exists
            
        except Exception as e:
            logger.error("Failed to check file existence", bucket=bucket, key=key, error=str(e))
            raise
    
    async def get_file_metadata(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """Get file metadata."""
        try:
            loop = asyncio.get_event_loop()
            
            def get_metadata():
                try:
                    response = self.s3_client.head_object(Bucket=bucket, Key=key)
                    return {
                        'size': response['ContentLength'],
                        'last_modified': response['LastModified'],
                        'etag': response['ETag'].strip('"'),
                        'content_type': response.get('ContentType'),
                        'metadata': response.get('Metadata', {})
                    }
                except ClientError as e:
                    if int(e.response['Error']['Code']) == 404:
                        return None
                    raise
            
            metadata = await loop.run_in_executor(None, get_metadata)
            return metadata
            
        except Exception as e:
            logger.error("Failed to get file metadata", bucket=bucket, key=key, error=str(e))
            raise
    
    async def delete_file(self, bucket: str, key: str) -> None:
        """Delete a file from storage."""
        try:
            loop = asyncio.get_event_loop()
            
            def delete():
                self.s3_client.delete_object(Bucket=bucket, Key=key)
            
            await loop.run_in_executor(None, delete)
            
            logger.info("Deleted file", bucket=bucket, key=key)
            
        except Exception as e:
            logger.error("Failed to delete file", bucket=bucket, key=key, error=str(e))
            raise
    
    def generate_file_path(self, user_id: str, video_id: str, filename: str) -> str:
        """Generate a standardized file path."""
        # Extract file extension
        parts = filename.rsplit('.', 1)
        extension = parts[1] if len(parts) > 1 else 'mp4'
        
        return f"{user_id}/{video_id}.{extension}"
    
    def generate_thumbnail_path(self, user_id: str, video_id: str) -> str:
        """Generate a standardized thumbnail path."""
        return f"{user_id}/{video_id}.jpg"
    
    def generate_processed_path(self, user_id: str, video_id: str, task_id: str) -> str:
        """Generate a standardized processed file path."""
        return f"{user_id}/{video_id}/{task_id}/output.mp4"

    def initiate_multipart_upload(self, key: str) -> str:
        """Initiate multipart upload and return upload ID."""
        try:
            bucket = self.config.bucket_raw
            response = self.s3_client.create_multipart_upload(
                Bucket=bucket,
                Key=key
            )
            return response['UploadId']
        except Exception as e:
            logger.error("Failed to initiate multipart upload", key=key, error=str(e))
            raise

    def upload_part(self, key: str, upload_id: str, part_number: int, data: bytes) -> str:
        """Upload a part and return ETag."""
        try:
            bucket = self.config.bucket_raw
            response = self.s3_client.upload_part(
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                PartNumber=part_number,
                Body=data
            )
            return response['ETag']
        except Exception as e:
            logger.error("Failed to upload part", key=key, part_number=part_number, error=str(e))
            raise

    def complete_multipart_upload(self, key: str, upload_id: str, parts: list) -> None:
        """Complete multipart upload."""
        try:
            bucket = self.config.bucket_raw
            self.s3_client.complete_multipart_upload(
                Bucket=bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
        except Exception as e:
            logger.error("Failed to complete multipart upload", key=key, error=str(e))
            raise

    def upload_file(self, local_path: str, key: str, bucket: Optional[str] = None) -> bool:
        """Upload file from local path to storage."""
        try:
            bucket_name = bucket or self.config.bucket_thumbnails
            self.s3_client.upload_file(local_path, bucket_name, key)
            return True
        except Exception as e:
            logger.error("Failed to upload file", local_path=local_path, key=key, error=str(e))
            return False

    def file_exists(self, key: str, bucket: Optional[str] = None) -> bool:
        """Check if file exists in storage."""
        try:
            bucket_name = bucket or self.config.bucket_thumbnails
            self.s3_client.head_object(Bucket=bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
        except Exception as e:
            logger.error("Failed to check file existence", key=key, error=str(e))
            return False

    def generate_internal_presigned_url(self, key: str, expires_in: int = 3600, bucket: Optional[str] = None) -> str:
        """
        Generate a presigned URL using the internal (container-to-container) endpoint.

        Use this when the URL is consumed server-side (e.g., passed to ffmpeg),
        not when the URL needs to be accessible from a browser.
        URL signing is a local HMAC operation – no network call is made.
        """
        try:
            bucket_name = bucket or self.config.bucket_raw
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': key},
                ExpiresIn=expires_in
            )
            logger.debug("Generated internal presigned URL", bucket=bucket_name, key=key)
            return url
        except Exception as e:
            logger.error("Failed to generate internal presigned URL", key=key, error=str(e))
            raise

    def generate_signed_url(self, key: str, expires_in: int = 3600, bucket: Optional[str] = None) -> str:
        """Generate signed URL for file access using public endpoint."""
        try:
            bucket_name = bucket or self.config.bucket_thumbnails
            # Use the public S3 client so URLs are accessible from browser
            url = self.s3_client_public.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': key},
                ExpiresIn=expires_in
            )
            return url
        except Exception as e:
            logger.error("Failed to generate signed URL", key=key, error=str(e))
            raise


# Global storage client instance
_storage_client: Optional[StorageClient] = None


def get_storage_client() -> StorageClient:
    """Get global storage client instance."""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient()
    return _storage_client


async def ensure_storage_ready() -> StorageClient:
    """Ensure storage is ready and buckets exist."""
    client = get_storage_client()
    await client.ensure_buckets_exist()
    return client
