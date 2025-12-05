"""
Path constants and utilities.

All paths are loaded from configuration to support different environments.
"""
import os
from pathlib import Path


def _get_settings():
    """Get settings, with fallback to environment variables."""
    try:
        from crownpipe.common.config import get_settings
        return get_settings()
    except Exception:
        # Fallback if settings not available yet
        return None


# Base directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

settings = _get_settings()
if settings:
    MEDIA_BASE = settings.media.base_dir
    DATA_BASE = settings.data.base_dir
else:
    MEDIA_BASE = Path(os.getenv('CROWNPIPE_MEDIA_BASE', '/srv/media'))
    DATA_BASE = Path(os.getenv('CROWNPIPE_DATA_BASE', '/srv/shares/marketing/filemaker'))

# Media pipeline directories
MEDIA_INBOX = MEDIA_BASE / "inbox"
MEDIA_PROCESSING = MEDIA_BASE / "processing"
MEDIA_PENDING_BG_REMOVAL = MEDIA_PROCESSING / "pending_bg_removal"
MEDIA_PENDING_FORMAT = MEDIA_PROCESSING / "pending_format"
MEDIA_REVIEW = MEDIA_BASE / "review"
MEDIA_BG_REMOVED = MEDIA_REVIEW / "bg_removed"
MEDIA_BG_REMOVAL_FAILED = MEDIA_REVIEW / "bg_removal_failed"
MEDIA_NAME_CONFLICTS = MEDIA_REVIEW / "name_conflicts"
MEDIA_READY_FOR_FORMATTING = MEDIA_BASE / "ready_for_formatting"
MEDIA_PRODUCTS = MEDIA_BASE / "products"
MEDIA_PRODUCTION = MEDIA_BASE / "production"
MEDIA_ARCHIVE = MEDIA_BASE / "archive"
MEDIA_ERRORS = MEDIA_BASE / "errors"

# Data pipeline directories
DATA_BACKUPS = DATA_BASE / "backups"
DATA_LOG_FILE = DATA_BACKUPS / "filemaker_import_report.txt"


def ensure_media_dirs() -> None:
    """Create all media pipeline directories if they don't exist."""
    for d in [
        MEDIA_INBOX,
        MEDIA_PROCESSING,
        MEDIA_PENDING_BG_REMOVAL,
        MEDIA_PENDING_FORMAT,
        MEDIA_REVIEW,
        MEDIA_BG_REMOVED,
        MEDIA_BG_REMOVAL_FAILED,
        MEDIA_NAME_CONFLICTS,
        MEDIA_READY_FOR_FORMATTING,
        MEDIA_PRODUCTS,
        MEDIA_PRODUCTION,
        MEDIA_ARCHIVE,
        MEDIA_ERRORS,
    ]:
        d.mkdir(parents=True, exist_ok=True)


def ensure_data_dirs() -> None:
    """Create all data pipeline directories if they don't exist."""
    for d in [DATA_BACKUPS]:
        d.mkdir(parents=True, exist_ok=True)


def get_product_dir(product_number: str) -> Path:
    """
    Get the product directory for a given product number.
    
    Args:
        product_number: Product number
        
    Returns:
        Path to product directory
    """
    return MEDIA_PRODUCTS / product_number


def get_product_source_dir(product_number: str) -> Path:
    """
    Get the source directory for a product.
    
    Args:
        product_number: Product number
        
    Returns:
        Path to product source directory
    """
    return get_product_dir(product_number) / "source"


def get_product_formats_dir(product_number: str) -> Path:
    """
    Get the formats directory for a product.
    
    Args:
        product_number: Product number
        
    Returns:
        Path to product formats directory
    """
    return get_product_dir(product_number) / "formats"


def get_production_dir(product_number: str) -> Path:
    """
    Get the production directory for a product.
    
    Args:
        product_number: Product number
        
    Returns:
        Path to production directory for product
    """
    return MEDIA_PRODUCTION / product_number
