"""
Storage client for S3-compatible object storage.

Handles file upload/download operations for video files using MinIO or Cloudflare R2
as specified in the worker specification.
"""

import boto3
import os
from typing import Optional
from botocore.exceptions import ClientError, NoCredentialsError
import structlog

from .config import get_config


class StorageClient:
    """
    S3-compatible storage client for video file operations.
    
    Supports both MinIO and Cloudflare R2 storage backends.
    """
    
    def __init__(self):
        self.config = get_config()
        self.logger = structlog.get_logger("storage_client")
        self.client = None
        self._setup_client()
    
    def _setup_client(self) -> None:
        """Set up boto3 S3 client based on configuration."""
        try:
            # Configure S3 client for MinIO or R2
            if self.config.storage.type == "minio":
                self.client = boto3.client(
                    's3',
                    endpoint_url=self.config.storage.endpoint,
                    aws_access_key_id=self.config.storage.access_key,
                    aws_secret_access_key=self.config.storage.secret_key,
                    region_name='us-east-1'  # MinIO default
                )
            elif self.config.storage.type == "r2":
                # Cloudflare R2 configuration
                self.client = boto3.client(
                    's3',
                    endpoint_url=self.config.storage.endpoint,
                    aws_access_key_id=self.config.storage.access_key,
                    aws_secret_access_key=self.config.storage.secret_key,
                    region_name='auto'  # R2 uses 'auto'
                )
            else:
                raise ValueError(f"Unsupported storage type: {self.config.storage.type}")
            
            self.logger.info("Storage client initialized", 
                           storage_type=self.config.storage.type,
                           endpoint=self.config.storage.endpoint)
            
        except Exception as e:
            self.logger.error("Failed to initialize storage client", error=str(e))
            raise
    
    def download_file(self, file_path: str, local_path: str, max_retries: int = 3) -> bool:
        """
        Download file from storage with retry logic.
        
        Args:
            file_path: Remote file path (e.g., "raw-videos/user-uuid/video-uuid.mp4")
            local_path: Local file path to save to
            max_retries: Maximum number of retry attempts
        
        Returns:
            True if download successful, False otherwise
        """
        bucket = self._get_bucket_from_path(file_path)
        key = self._get_key_from_path(file_path)
        
        for attempt in range(max_retries):
            try:
                # Ensure local directory exists
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                
                self.logger.info("Downloading file", 
                               file_path=file_path, 
                               local_path=local_path,
                               attempt=attempt + 1)
                
                self.client.download_file(bucket, key, local_path)
                
                # Verify file was downloaded
                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                    self.logger.info("File downloaded successfully", 
                                   file_path=file_path,
                                   local_path=local_path,
                                   size_bytes=os.path.getsize(local_path))
                    return True
                else:
                    raise Exception("Downloaded file is empty or missing")
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if error_code == 'NoSuchKey':
                    self.logger.error("File not found in storage", file_path=file_path)
                    return False
                else:
                    self.logger.warning("Storage error during download", 
                                      error=str(e), attempt=attempt + 1)
            except Exception as e:
                self.logger.warning("Error downloading file", 
                                  error=str(e), attempt=attempt + 1)
            
            if attempt < max_retries - 1:
                # Exponential backoff
                wait_time = 2 ** attempt
                self.logger.info("Retrying download", wait_seconds=wait_time)
                import time
                time.sleep(wait_time)
        
        self.logger.error("Failed to download file after retries", 
                         file_path=file_path, max_retries=max_retries)
        return False
    
    def upload_file(self, local_path: str, file_path: str, max_retries: int = 3) -> bool:
        """
        Upload file to storage with retry logic.
        
        Args:
            local_path: Local file path to upload
            file_path: Remote file path (e.g., "processed-videos/user-uuid/video-uuid/output.mp4")
            max_retries: Maximum number of retry attempts
        
        Returns:
            True if upload successful, False otherwise
        """
        if not os.path.exists(local_path):
            self.logger.error("Local file not found for upload", local_path=local_path)
            return False
        
        bucket = self._get_bucket_from_path(file_path)
        key = self._get_key_from_path(file_path)
        
        for attempt in range(max_retries):
            try:
                self.logger.info("Uploading file", 
                               local_path=local_path,
                               file_path=file_path,
                               attempt=attempt + 1)
                
                # Upload with progress callback
                file_size = os.path.getsize(local_path)
                
                self.client.upload_file(
                    local_path, 
                    bucket, 
                    key,
                    ExtraArgs={'ContentType': self._get_content_type(local_path)}
                )
                
                # Verify upload
                try:
                    response = self.client.head_object(Bucket=bucket, Key=key)
                    uploaded_size = response['ContentLength']
                    
                    if uploaded_size == file_size:
                        self.logger.info("File uploaded successfully", 
                                       file_path=file_path,
                                       size_bytes=file_size)
                        return True
                    else:
                        raise Exception(f"Size mismatch: local={file_size}, uploaded={uploaded_size}")
                        
                except ClientError:
                    raise Exception("Failed to verify uploaded file")
                
            except Exception as e:
                self.logger.warning("Error uploading file", 
                                  error=str(e), attempt=attempt + 1)
            
            if attempt < max_retries - 1:
                # Exponential backoff
                wait_time = 2 ** attempt
                self.logger.info("Retrying upload", wait_seconds=wait_time)
                import time
                time.sleep(wait_time)
        
        self.logger.error("Failed to upload file after retries", 
                         file_path=file_path, max_retries=max_retries)
        return False
    
    def _get_bucket_from_path(self, file_path: str) -> str:
        """
        Determine bucket name from file path.
        
        Args:
            file_path: File path starting with bucket-like prefix
        
        Returns:
            Bucket name
        """
        if file_path.startswith("raw-videos/"):
            return self.config.storage.bucket_raw
        elif file_path.startswith("processed-videos/"):
            return self.config.storage.bucket_processed
        else:
            # Default to raw bucket for unknown paths
            self.logger.warning("Unknown file path prefix, using raw bucket", 
                              file_path=file_path)
            return self.config.storage.bucket_raw
    
    def _get_key_from_path(self, file_path: str) -> str:
        """
        Extract object key from file path.
        
        Args:
            file_path: Full file path
        
        Returns:
            Object key (path without bucket prefix)
        """
        if file_path.startswith("raw-videos/"):
            return file_path[len("raw-videos/"):]
        elif file_path.startswith("processed-videos/"):
            return file_path[len("processed-videos/"):]
        else:
            # Return as-is if no known prefix
            return file_path
    
    def _get_content_type(self, file_path: str) -> str:
        """
        Determine content type based on file extension.
        
        Args:
            file_path: File path
        
        Returns:
            MIME content type
        """
        extension = os.path.splitext(file_path)[1].lower()
        
        content_types = {
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.mkv': 'video/x-matroska'
        }
        
        return content_types.get(extension, 'application/octet-stream')
