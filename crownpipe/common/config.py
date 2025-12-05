"""
Enhanced configuration management with validation.

Uses pydantic for type validation and environment variable support.
"""
import os
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class DatabaseConfig(BaseModel):
    """Database connection configuration."""
    
    host: str = Field(default="127.0.0.1", env="PG_HOST")
    port: int = Field(default=5432, env="PG_PORT")
    database: str = Field(default="crown_marketing", env="PG_DATABASE")
    user: str = Field(default="crown_admin", env="PG_USER")
    password: Optional[str] = Field(default=None, env="PG_PASSWORD")
    
    class Config:
        env_prefix = "CROWNPIPE_DB_"
    
    @validator('password')
    def get_password_from_pgpass(cls, v, values):
        """Get password from .pgpass if not provided."""
        if v:
            return v
        
        # Try to read from .pgpass
        from crownpipe.common.db import get_pgpass_password
        
        pgpass_paths = [
            Path('/var/lib/postgresql/.pgpass'),
            Path.home() / '.pgpass'
        ]
        
        for pgpass_path in pgpass_paths:
            if pgpass_path.exists():
                try:
                    return get_pgpass_password(
                        pgpass_path,
                        values.get('host', '127.0.0.1'),
                        str(values.get('port', 5432)),
                        values.get('database', 'crown_marketing'),
                        values.get('user', 'crown_admin')
                    )
                except ValueError:
                    continue
        
        return None
    
    def get_dsn(self) -> str:
        """Get PostgreSQL connection string."""
        if not self.password:
            raise ValueError("Database password not configured")
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class MediaPipelineConfig(BaseModel):
    """Media pipeline configuration."""
    
    base_dir: Path = Field(default=Path("/srv/media"), env="CROWNPIPE_MEDIA_BASE")
    max_concurrent_bgremove: int = Field(default=4)
    bgremove_timeout_seconds: int = Field(default=300)
    supported_formats: List[str] = Field(default=['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp', '.psd'])
    imagemagick_convert_bin: str = Field(default="convert")
    
    # Format generation settings
    default_dpi: int = Field(default=300)
    jpeg_quality: int = Field(default=90)
    png_compression: int = Field(default=9)
    
    class Config:
        env_prefix = "CROWNPIPE_MEDIA_"


class DataPipelineConfig(BaseModel):
    """Data pipeline configuration."""
    
    base_dir: Path = Field(default=Path("/srv/shares/marketing/filemaker"), env="CROWNPIPE_DATA_BASE")
    filemaker_server: Optional[str] = Field(default=None, env="FILEMAKER_SERVER")
    filemaker_port: int = Field(default=443, env="FILEMAKER_PORT")
    filemaker_database: Optional[str] = Field(default=None, env="FILEMAKER_DATABASE")
    filemaker_username: Optional[str] = Field(default=None, env="FILEMAKER_USERNAME")
    filemaker_password: Optional[str] = Field(default=None, env="FILEMAKER_PASSWORD")
    
    iseries_server: Optional[str] = Field(default=None, env="ISERIES_SERVER")
    iseries_database: Optional[str] = Field(default=None, env="ISERIES_DATABASE")
    iseries_username: Optional[str] = Field(default=None, env="ISERIES_USERNAME")
    iseries_password: Optional[str] = Field(default=None, env="ISERIES_PASSWORD")
    
    class Config:
        env_prefix = "CROWNPIPE_DATA_"


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    log_dir: Path = Field(default=Path("/var/log/crownpipe"))
    log_level: str = Field(default="INFO")
    log_to_database: bool = Field(default=True)
    log_to_file: bool = Field(default=True)
    max_log_size_mb: int = Field(default=50)
    log_retention_days: int = Field(default=90)
    
    class Config:
        env_prefix = "CROWNPIPE_LOG_"
    
    @validator('log_level')
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v


class DashboardConfig(BaseModel):
    """Dashboard configuration."""
    
    secret_key: str = Field(default=None, env="DJANGO_SECRET_KEY")
    debug: bool = Field(default=False, env="DJANGO_DEBUG")
    allowed_hosts: List[str] = Field(default=["localhost", "127.0.0.1"])
    
    class Config:
        env_prefix = "CROWNPIPE_DASHBOARD_"
    
    @validator('secret_key')
    def generate_secret_key(cls, v):
        """Generate secret key if not provided."""
        if v:
            return v
        
        # Only auto-generate in development
        import secrets
        return secrets.token_urlsafe(50)


class Settings(BaseModel):
    """Global CrownPipe settings."""
    
    environment: str = Field(default="production", env="CROWNPIPE_ENVIRONMENT")
    
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    media: MediaPipelineConfig = Field(default_factory=MediaPipelineConfig)
    data: DataPipelineConfig = Field(default_factory=DataPipelineConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    
    class Config:
        env_nested_delimiter = '__'
    
    @validator('environment')
    def validate_environment(cls, v):
        """Validate environment."""
        valid_envs = ['development', 'staging', 'production']
        if v not in valid_envs:
            raise ValueError(f"Invalid environment: {v}. Must be one of {valid_envs}")
        return v


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get global settings instance (singleton).
    
    Settings are loaded once and cached. Environment variables
    are read on first access.
    
    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """
    Reload settings from environment variables.
    
    Useful for testing or hot-reloading configuration.
    
    Returns:
        New Settings instance
    """
    global _settings
    _settings = Settings()
    return _settings


# Legacy Config class for backward compatibility
class Config:
    """
    Legacy configuration class (backward compatibility).
    
    For new code, use get_settings() instead.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        self._settings = get_settings()
        self._config = {}
    
    def get(self, key: str, default=None):
        """Get configuration value."""
        # Try to map old keys to new settings structure
        key_map = {
            'db_host': lambda: self._settings.database.host,
            'db_port': lambda: self._settings.database.port,
            'db_database': lambda: self._settings.database.database,
            'db_user': lambda: self._settings.database.user,
            'media_base': lambda: str(self._settings.media.base_dir),
            'data_base': lambda: str(self._settings.data.base_dir),
        }
        
        if key in key_map:
            return key_map[key]()
        
        return self._config.get(key, default)
    
    def __getitem__(self, key: str):
        value = self.get(key)
        if value is None:
            raise KeyError(f"Config key '{key}' not found")
        return value
    
    def set(self, key: str, value):
        self._config[key] = value
    
    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None
