"""Configuration management for the dashcam backend service."""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path


@dataclass
class MongoDBConfig:
    """MongoDB configuration."""
    uri: str = "mongodb://admin:dashcam123@localhost:27017/dashcam_db"
    database_name: str = "dashcam_db"
    
    @classmethod
    def from_env(cls) -> "MongoDBConfig":
        return cls(
            uri=os.getenv("MONGODB_URI", cls.uri),
            database_name=os.getenv("DATABASE_NAME", cls.database_name),
        )


@dataclass
class RabbitMQConfig:
    """RabbitMQ configuration."""
    host: str = "localhost"
    port: int = 5672
    username: str = "dashcam"
    password: str = "dashcam123"
    connection_timeout: int = 30
    retry_delay: int = 5
    max_retries: int = 5
    
    @classmethod
    def from_env(cls) -> "RabbitMQConfig":
        return cls(
            host=os.getenv("RABBITMQ_HOST", cls.host),
            port=int(os.getenv("RABBITMQ_PORT", str(cls.port))),
            username=os.getenv("RABBITMQ_USER", cls.username),
            password=os.getenv("RABBITMQ_PASSWORD", cls.password),
            connection_timeout=int(os.getenv("RABBITMQ_CONNECTION_TIMEOUT", str(cls.connection_timeout))),
            retry_delay=int(os.getenv("RABBITMQ_RETRY_DELAY", str(cls.retry_delay))),
            max_retries=int(os.getenv("RABBITMQ_MAX_RETRIES", str(cls.max_retries))),
        )


@dataclass
class StorageConfig:
    """Storage configuration for S3-compatible storage."""
    storage_type: str = "minio"  # or 'r2'
    endpoint: str = "http://localhost:9000"
    endpoint_public: str = "http://localhost:9000"  # Public endpoint for pre-signed URLs
    access_key: str = "AKIAADMIN87654321"
    secret_key: str = "admin-secret-key-secure-dashcam-2024"
    bucket_raw: str = "dashcam-raw-videos"
    bucket_processed: str = "dashcam-processed-videos"
    bucket_temp: str = "dashcam-temp-uploads"
    bucket_thumbnails: str = "dashcam-thumbnails"
    region: str = "us-east-1"
    
    @classmethod
    def from_env(cls) -> "StorageConfig":
        return cls(
            storage_type=os.getenv("STORAGE_TYPE", cls.storage_type),
            endpoint=os.getenv("STORAGE_ENDPOINT", cls.endpoint),
            endpoint_public=os.getenv("STORAGE_ENDPOINT_PUBLIC", os.getenv("STORAGE_ENDPOINT", cls.endpoint_public)),
            access_key=os.getenv("STORAGE_ACCESS_KEY", cls.access_key),
            secret_key=os.getenv("STORAGE_SECRET_KEY", cls.secret_key),
            bucket_raw=os.getenv("STORAGE_BUCKET_RAW", cls.bucket_raw),
            bucket_processed=os.getenv("STORAGE_BUCKET_PROCESSED", cls.bucket_processed),
            bucket_temp=os.getenv("STORAGE_BUCKET_TEMP", cls.bucket_temp),
            bucket_thumbnails=os.getenv("STORAGE_BUCKET_THUMBNAILS", cls.bucket_thumbnails),
            region=os.getenv("STORAGE_REGION", cls.region),
        )


@dataclass
class UploadConfig:
    """Upload service configuration."""
    service_url: str = "http://localhost:8001"
    max_upload_size: int = 2147483648  # 2GB
    allowed_formats: List[str] = field(default_factory=lambda: ["mp4", "avi", "mov", "mkv"])
    
    @classmethod
    def from_env(cls) -> "UploadConfig":
        allowed_formats = os.getenv("ALLOWED_VIDEO_FORMATS", "mp4,avi,mov,mkv").split(",")
        return cls(
            service_url=os.getenv("UPLOAD_SERVICE_URL", cls.service_url),
            max_upload_size=int(os.getenv("MAX_UPLOAD_SIZE", str(cls.max_upload_size))),
            allowed_formats=allowed_formats,
        )


@dataclass
class AuthConfig:
    """Authentication configuration."""
    google_client_id: str = ""
    google_client_secret: str = ""
    # Must be set via SESSION_SECRET_KEY env var in production
    session_secret_key: str = ""
    session_expires_hours: int = 24
    
    @classmethod
    def from_env(cls) -> "AuthConfig":
        return cls(
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", cls.google_client_id),
            google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", cls.google_client_secret),
            session_secret_key=os.getenv("SESSION_SECRET_KEY", cls.session_secret_key),
            session_expires_hours=int(os.getenv("SESSION_EXPIRES_HOURS", str(cls.session_expires_hours))),
        )


@dataclass
class PaymentConfig:
    """Payment configuration (optional)."""
    enabled: bool = False
    merchant_id: str = ""
    credit_price_per_minute: float = 0.10
    
    @classmethod
    def from_env(cls) -> "PaymentConfig":
        return cls(
            enabled=os.getenv("GOOGLE_PAY_ENABLED", "false").lower() == "true",
            merchant_id=os.getenv("GOOGLE_PAY_MERCHANT_ID", cls.merchant_id),
            credit_price_per_minute=float(os.getenv("CREDIT_PRICE_PER_MINUTE", str(cls.credit_price_per_minute))),
        )


@dataclass
class CleanupConfig:
    """Auto-deletion configuration for old video files."""
    enabled: bool = True
    max_age_days: int = 7
    interval_hours: int = 1

    @classmethod
    def from_env(cls) -> "CleanupConfig":
        return cls(
            enabled=os.getenv("FILE_CLEANUP_ENABLED", "true").lower() == "true",
            max_age_days=int(os.getenv("FILE_CLEANUP_MAX_AGE_DAYS", str(cls.max_age_days))),
            interval_hours=int(os.getenv("FILE_CLEANUP_INTERVAL_HOURS", str(cls.interval_hours))),
        )


@dataclass
class AppConfig:
    """Application configuration."""
    log_level: str = "INFO"
    worker_id: str = ""
    hostname: str = ""
    default_processing_settings: Dict[str, Any] = field(default_factory=dict)
    
    # Connection monitoring settings
    connection_health_check_interval: int = 30  # seconds
    connection_retry_max_attempts: int = 10
    connection_retry_base_delay: float = 1.0  # seconds
    connection_retry_max_delay: float = 60.0  # seconds
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        import socket
        import uuid
        
        hostname = socket.gethostname()
        worker_id = os.getenv("WORKER_ID", str(uuid.uuid4()))
        
        return cls(
            log_level=os.getenv("LOG_LEVEL", cls.log_level),
            worker_id=worker_id,
            hostname=hostname,
            default_processing_settings={},  # Will be populated from environment if needed
            connection_health_check_interval=int(os.getenv("CONNECTION_HEALTH_CHECK_INTERVAL", "30")),
            connection_retry_max_attempts=int(os.getenv("CONNECTION_RETRY_MAX_ATTEMPTS", "10")),
            connection_retry_base_delay=float(os.getenv("CONNECTION_RETRY_BASE_DELAY", "1.0")),
            connection_retry_max_delay=float(os.getenv("CONNECTION_RETRY_MAX_DELAY", "60.0")),
        )


@dataclass
class BackendConfig:
    """Complete backend service configuration."""
    mongodb: MongoDBConfig
    rabbitmq: RabbitMQConfig
    storage: StorageConfig
    upload: UploadConfig
    auth: AuthConfig
    payment: PaymentConfig
    app: AppConfig
    cleanup: CleanupConfig = None

    def __post_init__(self):
        if self.cleanup is None:
            self.cleanup = CleanupConfig()

    @classmethod
    def from_env(cls) -> "BackendConfig":
        return cls(
            mongodb=MongoDBConfig.from_env(),
            rabbitmq=RabbitMQConfig.from_env(),
            storage=StorageConfig.from_env(),
            upload=UploadConfig.from_env(),
            auth=AuthConfig.from_env(),
            payment=PaymentConfig.from_env(),
            app=AppConfig.from_env(),
            cleanup=CleanupConfig.from_env(),
        )


# Global configuration instance
_config: Optional[BackendConfig] = None


def get_config() -> BackendConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = BackendConfig.from_env()
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None


def load_env_file(env_path: Optional[Path] = None) -> None:
    """Load environment variables from .env file."""
    try:
        from dotenv import load_dotenv
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()
    except ImportError:
        # dotenv not available, skip
        pass
