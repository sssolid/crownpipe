#!/usr/bin/env python3
"""
Background removal pipeline.
- Processes files from pending_bg_removal
- Removes background using rembg
- Saves to review directory for human inspection
- Creates audit trail
"""
import subprocess
from datetime import datetime
from pathlib import Path

from rembg import remove

from crownpipe.common.logger import get_logger
from crownpipe.common.paths import (
    MEDIA_PENDING_BG_REMOVAL,
    MEDIA_BG_REMOVED,
    MEDIA_BG_REMOVAL_FAILED,
    MEDIA_ARCHIVE,
    ensure_media_dirs,
)
from crownpipe.media.fileutils import (
    is_image_file,
    wait_for_complete_file,
    safe_move,
    move_to_errors,
    extract_product_number,
    get_view_suffix,
)

logger = get_logger(__name__)

CONVERT_BIN = "convert"


def run_convert(args, input_bytes: bytes | None = None) -> bytes:
    """
    Run ImageMagick 'convert' with the given argument list.

    Args:
        args: List of arguments (excluding binary name)
        input_bytes: Optional input data via stdin

    Returns:
        stdout bytes

    Raises:
        RuntimeError: If convert fails
    """
    cmd = [CONVERT_BIN] + args
    try:
        result = subprocess.run(
            cmd,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="ignore")
        raise RuntimeError(
            f"convert failed: {' '.join(cmd)}\n{stderr}"
        ) from e
    return result.stdout


def source_to_png_bytes(src: Path) -> bytes:
    """
    Convert any input format to standardized PNG.

    Args:
        src: Source image path

    Returns:
        PNG bytes (RGBA, 8-bit, sRGB)
    """
    logger.info(f"Normalizing {src.name} to PNG via ImageMagick")
    return run_convert([
        str(src),
        "-alpha", "on",
        "-colorspace", "sRGB",
        "-strip",
        "PNG32:-",  # RGBA, 8-bit, written to stdout
    ])


def trim_png_bytes(png_bytes: bytes) -> bytes:
    """
    Trim transparent borders from PNG.

    Args:
        png_bytes: Input PNG bytes

    Returns:
        Trimmed PNG bytes
    """
    logger.info("Trimming PNG")
    return run_convert([
        "PNG:-",
        "-alpha", "on",
        "-colorspace", "sRGB",
        "-trim", "+repage",
        "PNG32:-",
    ], input_bytes=png_bytes)


def process_bg_removal(src: Path):
    """
    Process a single file through background removal.
    ALL results (success or failure) go to review folder for human inspection.

    Note: Audit log is created in rename_incoming.py (captures uploader) and
    prepare_formatting.py (captures approval). No audit entry here since
    product directory doesn't exist yet and background removal is just an
    intermediate step before human review.

    Args:
        src: Source file in pending_bg_removal
    """
    logger.info(f"Processing {src.name}")

    # Wait for file stability
    if not wait_for_complete_file(src):
        move_to_errors(src, "File never stabilized before bg removal")
        return

    # Extract product info
    product_number = extract_product_number(src.name)
    if not product_number:
        move_to_errors(src, "Could not extract product number")
        return

    view_suffix = get_view_suffix(src.name)

    bg_removed_success = False
    output_png = None

    try:
        # Step 1: Normalize to PNG
        base_png = source_to_png_bytes(src)

        # Step 2: Background removal
        logger.info(f"Running rembg on {src.name}")
        bg_removed_png = remove(base_png)

        # Step 3: Trim
        trimmed_png = trim_png_bytes(bg_removed_png)

        output_png = trimmed_png
        bg_removed_success = True

    except Exception as e:
        logger.error(f"Background removal failed for {src.name}: {e}")
        # On failure, we'll just normalize the original for manual editing
        try:
            output_png = source_to_png_bytes(src)
        except Exception as e2:
            move_to_errors(src, f"BG removal failed and couldn't normalize: {e}, {e2}")
            return

    # Save result to review folder for human inspection
    try:
        # Determine destination based on success/failure
        if bg_removed_success:
            dest_dir = MEDIA_BG_REMOVED
            status = "success"
        else:
            dest_dir = MEDIA_BG_REMOVAL_FAILED
            status = "failed"

        dest_dir.mkdir(parents=True, exist_ok=True)

        # Build output filename - keep original name for easy tracking
        output_name = f"{product_number}{view_suffix}.png"
        output_path = dest_dir / output_name

        # Write the processed image
        with open(output_path, "wb") as f:
            f.write(output_png)
        logger.info(f"Saved to review ({status}): {output_path}")

        # Archive the original file
        year_month = datetime.now().strftime("%Y-%m")
        archive_dir = MEDIA_ARCHIVE / year_month / product_number
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / src.name

        safe_move(src, archive_path)
        logger.info(f"Archived original: {archive_path}")

    except Exception as e:
        move_to_errors(src, f"Failed to save to review folder: {e}")


def main():
    """Process all files pending background removal."""
    ensure_media_dirs()

    for entry in MEDIA_PENDING_BG_REMOVAL.iterdir():
        if not is_image_file(entry):
            continue

        try:
            process_bg_removal(entry)
        except Exception as e:
            logger.error(f"Unexpected error processing {entry}: {e}")
            move_to_errors(entry, f"Unexpected error in bgremove: {e}")


if __name__ == "__main__":
    main()
