#!/usr/bin/env python3
"""
File utilities for media pipeline.

This module contains file-specific utilities.
Path constants have been moved to crownpipe.common.paths.
"""
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from crownpipe.common.logger import get_logger
from crownpipe.common.paths import MEDIA_ERRORS

logger = get_logger(__name__)

# Supported image extensions
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".psd"}


def is_image_file(path: Path) -> bool:
    """
    Check if file is a supported image type.
    
    Args:
        path: Path to check
        
    Returns:
        True if file is a supported image format
    """
    return path.is_file() and path.suffix.lower() in IMAGE_EXTS


def wait_for_complete_file(path: Path, retries: int = 10, delay: float = 0.5) -> bool:
    """
    Wait for file to finish being written by checking if size stabilizes.
    
    Args:
        path: Path to file
        retries: Number of times to check
        delay: Seconds to wait between checks
        
    Returns:
        True if file is complete, False otherwise
    """
    last_size = -1
    for _ in range(retries):
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            time.sleep(delay)
            continue

        if size == last_size and size > 0:
            return True

        last_size = size
        time.sleep(delay)

    logger.warning(f"File {path} did not stabilize; treating as incomplete")
    return False


def safe_move(src: Path, dst: Path) -> None:
    """
    Safely move a file, creating parent directories as needed.
    
    Args:
        src: Source path
        dst: Destination path
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Moving {src} → {dst}")
    shutil.move(str(src), str(dst))


def move_to_errors(src: Path, reason: str) -> None:
    """
    Move file to errors directory with timestamp and reason.
    
    Args:
        src: Source file
        reason: Reason for error
    """
    logger.error(f"Error processing {src}: {reason}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = MEDIA_ERRORS / f"{timestamp}_{src.name}"
    
    try:
        safe_move(src, dst)
        
        # Write error reason to companion text file
        error_file = dst.with_suffix(dst.suffix + ".error.txt")
        with open(error_file, "w") as f:
            f.write(f"File: {src.name}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Reason: {reason}\n")
    except Exception as e:
        logger.error(f"Failed to move {src} to errors: {e}")


def extract_product_number(filename: str) -> Optional[str]:
    """
    Extract product number from filename.
    
    Expected format: NUMBER.ext or NUMBER_VIEW.ext
    
    Args:
        filename: Filename to parse
        
    Returns:
        Product number or None if invalid
    """
    stem = Path(filename).stem
    
    # Handle NUMBER_VIEW format
    if "_" in stem:
        parts = stem.split("_")
        # Check if last part is numeric (view number)
        if parts[-1].isdigit():
            return "_".join(parts[:-1])
        return "_".join(parts)
    
    return stem


def get_view_suffix(filename: str) -> str:
    """
    Get the view suffix from a filename.
    
    Args:
        filename: Filename to parse
        
    Returns:
        View suffix (e.g., '_1', '_2') or empty string
    """
    stem = Path(filename).stem
    
    if "_" in stem:
        parts = stem.split("_")
        if parts[-1].isdigit():
            return f"_{parts[-1]}"
    
    return ""


def normalize_product_number(product_number: str) -> str:
    """
    Normalize product number to uppercase with underscores.
    
    Args:
        product_number: Raw product number
        
    Returns:
        Normalized product number
    """
    return product_number.upper().replace(" ", "_").replace("-", "_")
