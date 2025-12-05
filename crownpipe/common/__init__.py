"""
Common utilities shared across CrownPipe modules.
"""

from crownpipe.common.config import Config, get_settings
from crownpipe.common.db import get_conn, test_connection
from crownpipe.common.exceptions import (
    ConfigurationError,
    CrownPipeError,
    DatabaseError,
    DataPipelineError,
    ExternalServiceError,
    FileProcessingError,
    MediaPipelineError,
    PipelineError,
    SyncPipelineError,
    ValidationError,
)
from crownpipe.common.logger import (
    PipelineLogger,
    get_logger,
    get_pipeline_logger,
    setup_logging,
)
from crownpipe.common.paths import (
    DATA_BASE,
    MEDIA_BASE,
    MEDIA_INBOX,
    MEDIA_PRODUCTS,
    ensure_data_dirs,
    ensure_media_dirs,
    get_product_dir,
    get_product_formats_dir,
    get_product_source_dir,
    get_production_dir,
)

__all__ = [
    # Configuration
    'Config',
    'get_settings',
    
    # Database
    'get_conn',
    'test_connection',
    
    # Logging
    'get_logger',
    'get_pipeline_logger',
    'PipelineLogger',
    'setup_logging',
    
    # Exceptions
    'CrownPipeError',
    'ConfigurationError',
    'DatabaseError',
    'PipelineError',
    'MediaPipelineError',
    'DataPipelineError',
    'SyncPipelineError',
    'FileProcessingError',
    'ValidationError',
    'ExternalServiceError',
    
    # Paths
    'MEDIA_BASE',
    'MEDIA_INBOX',
    'MEDIA_PRODUCTS',
    'DATA_BASE',
    'ensure_media_dirs',
    'ensure_data_dirs',
    'get_product_dir',
    'get_product_source_dir',
    'get_product_formats_dir',
    'get_production_dir',
]
