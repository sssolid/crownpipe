#!/usr/bin/env python3
"""
Process human-approved images from ready_for_formatting.
This creates the product directory structure and prepares for formatting.
Only runs on files that humans have manually moved to ready_for_formatting.
"""
from pathlib import Path

from crownpipe.common.logger import get_logger
from crownpipe.common.paths import (
    MEDIA_READY_FOR_FORMATTING,
    ensure_media_dirs,
    get_product_dir,
    get_product_source_dir,
)
from crownpipe.media.audit import AuditLog
from crownpipe.media.fileutils import (
    is_image_file,
    extract_product_number,
    get_view_suffix,
    safe_move,
    move_to_errors,
)

logger = get_logger(__name__)


def prepare_for_formatting(src: Path):
    """
    Move human-approved image to product source directory.
    Creates audit log and prepares for format generation.

    Args:
        src: Source file in ready_for_formatting
    """
    logger.info(f"Preparing {src.name} for formatting")

    # Extract product info
    product_number = extract_product_number(src.name)
    if not product_number:
        move_to_errors(src, "Could not extract product number")
        return

    view_suffix = get_view_suffix(src.name)

    try:
        # Create product directory structure
        product_dir = get_product_dir(product_number)
        source_dir = get_product_source_dir(product_number)
        source_dir.mkdir(parents=True, exist_ok=True)

        # Build target filename
        target_name = f"{product_number}{view_suffix}.png"
        target_path = source_dir / target_name

        # Move to products directory
        safe_move(src, target_path)
        logger.info(f"Moved to products: {target_path}")

        # Create/update audit log (username was captured at upload time)
        AuditLog.create_or_update(
            product_dir,
            product_number,
            "human_approved",
            user="system",  # Username already captured during initial upload
            details=f"Human reviewed and approved {src.name} for formatting"
        )

        logger.info(f"Product {product_number} ready for format generation")

    except Exception as e:
        move_to_errors(src, f"Failed to prepare for formatting: {e}")


def main():
    """Process all files in ready_for_formatting directory."""
    ensure_media_dirs()

    if not MEDIA_READY_FOR_FORMATTING.exists():
        logger.info("ready_for_formatting directory does not exist")
        return

    files_processed = 0
    for entry in MEDIA_READY_FOR_FORMATTING.iterdir():
        if not is_image_file(entry):
            continue

        try:
            prepare_for_formatting(entry)
            files_processed += 1
        except Exception as e:
            logger.error(f"Unexpected error processing {entry}: {e}")
            move_to_errors(entry, f"Unexpected error: {e}")

    if files_processed > 0:
        logger.info(f"Processed {files_processed} approved images")


if __name__ == "__main__":
    main()
