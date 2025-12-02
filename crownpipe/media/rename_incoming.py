#!/usr/bin/env python3
"""
Process incoming files from inbox.

- Validates filenames
- Normalizes product numbers
- Moves to pending_bg_removal
- Creates initial audit entry
"""
from pathlib import Path

from crownpipe.common.logger import get_logger
from crownpipe.common.paths import (
    MEDIA_INBOX,
    MEDIA_PENDING_BG_REMOVAL,
    MEDIA_NAME_CONFLICTS,
    ensure_media_dirs,
    get_product_dir,
)
from crownpipe.media.audit import AuditLog
from crownpipe.media.fileutils import (
    is_image_file,
    wait_for_complete_file,
    safe_move,
    move_to_errors,
    extract_product_number,
    normalize_product_number,
    get_view_suffix,
)

logger = get_logger(__name__)


def validate_filename(path: Path) -> tuple[bool, str]:
    """
    Validate that filename follows expected format.

    Args:
        path: File to validate

    Returns:
        (is_valid, reason) tuple
    """
    stem = path.stem

    # Check if we can extract a product number
    product_number = extract_product_number(stem)
    if not product_number:
        return False, "Could not extract product number from filename"

    # Check for invalid characters
    invalid_chars = set('<>:"|?*')
    if any(c in stem for c in invalid_chars):
        return False, f"Filename contains invalid characters: {invalid_chars}"

    return True, "Valid"


def process_incoming_file(src: Path) -> None:
    """
    Process a single file from inbox.

    Args:
        src: Source file in inbox
    """
    logger.info(f"Processing {src.name}")

    # Wait for file to be completely uploaded
    if not wait_for_complete_file(src):
        move_to_errors(src, "File never stabilized (likely incomplete upload)")
        return

    # Validate filename
    is_valid, reason = validate_filename(src)
    if not is_valid:
        logger.warning(f"Invalid filename {src.name}: {reason}")
        # Move to name_conflicts for human review
        conflict_path = MEDIA_NAME_CONFLICTS / src.name
        safe_move(src, conflict_path)
        return

    # Extract and normalize product number
    raw_product_number = extract_product_number(src.name)
    product_number = normalize_product_number(raw_product_number)
    view_suffix = get_view_suffix(src.name)

    # Build target filename
    ext = src.suffix.lower()
    target_name = f"{product_number}{view_suffix}{ext}"
    target_path = MEDIA_PENDING_BG_REMOVAL / target_name

    # Check for conflicts
    counter = 1
    while target_path.exists():
        # File already exists in pending - might be duplicate upload
        logger.warning(f"File {target_name} already exists in pending_bg_removal")
        target_path = MEDIA_PENDING_BG_REMOVAL / f"{product_number}{view_suffix}_{counter}{ext}"
        counter += 1

        if counter > 100:
            move_to_errors(src, "Too many duplicate files")
            return

    try:
        # Get username from file BEFORE moving (captures original Samba uploader)
        username = AuditLog.get_samba_username(src)

        # Create product directory and initial audit entry
        product_dir = get_product_dir(product_number)
        product_dir.mkdir(parents=True, exist_ok=True)

        AuditLog.create_or_update(
            product_dir,
            product_number,
            "initial_upload",
            user=username,
            source_file=src,
            details=f"File uploaded: {src.name}"
        )

        # Move to pending
        safe_move(src, target_path)

        logger.info(f"Moved {src.name} → {target_path.name} (uploaded by {username})")

    except Exception as e:
        move_to_errors(src, f"Failed to process: {e}")


def main():
    """Process all files in inbox."""
    ensure_media_dirs()

    # Process all image files in inbox
    for entry in MEDIA_INBOX.iterdir():
        if not entry.is_file():
            continue

        if not is_image_file(entry):
            move_to_errors(entry, "Not a supported image type")
            continue

        try:
            process_incoming_file(entry)
        except Exception as e:
            logger.error(f"Unexpected error processing {entry}: {e}")
            move_to_errors(entry, f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
