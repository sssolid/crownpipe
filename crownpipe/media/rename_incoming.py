#!/usr/bin/env python3
"""
Process incoming files from inbox.

- Validates filenames
- Normalizes product numbers
- Moves to pending_bg_removal
- Creates initial audit entry
"""
from pathlib import Path
from typing import Iterable

from crownpipe.common.exceptions import FileProcessingError, ValidationError
from crownpipe.common.paths import (
    MEDIA_INBOX,
    MEDIA_NAME_CONFLICTS,
    MEDIA_PENDING_BG_REMOVAL,
    ensure_media_dirs,
    get_product_dir,
)
from crownpipe.common.pipeline import FileProcessingPipeline
from crownpipe.media.audit import AuditLog
from crownpipe.media.fileutils import (
    extract_product_number,
    get_view_suffix,
    is_image_file,
    move_to_errors,
    normalize_product_number,
    safe_move,
    wait_for_complete_file,
)


class RenameIncomingPipeline(FileProcessingPipeline):
    """Pipeline for processing incoming files from inbox."""
    
    def __init__(self):
        super().__init__(source_dir=MEDIA_INBOX, pipeline_name='rename_incoming')
        ensure_media_dirs()
    
    def get_items(self) -> Iterable[Path]:
        """Get image files from inbox."""
        if not self.source_dir.exists():
            return []
        
        return [f for f in self.source_dir.iterdir() if f.is_file() and is_image_file(f)]
    
    def validate_filename(self, path: Path) -> tuple[bool, str]:
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
            return False, f"Filename contains invalid characters"
        
        return True, "Valid"
    
    def process_item(self, src: Path) -> bool:
        """
        Process a single file from inbox.
        
        Args:
            src: Source file in inbox
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Processing {src.name}")
        
        # Wait for file to be completely uploaded
        if not wait_for_complete_file(src):
            move_to_errors(src, "File never stabilized (likely incomplete upload)")
            return False
        
        # Validate filename
        is_valid, reason = self.validate_filename(src)
        if not is_valid:
            self.logger.warning(f"Invalid filename {src.name}: {reason}")
            # Move to name_conflicts for human review
            conflict_path = MEDIA_NAME_CONFLICTS / src.name
            safe_move(src, conflict_path)
            return False
        
        # Extract and normalize product number
        raw_product_number = extract_product_number(src.name)
        if not raw_product_number:
            move_to_errors(src, "Could not extract product number")
            return False
        
        product_number = normalize_product_number(raw_product_number)
        view_suffix = get_view_suffix(src.name)
        
        # Build target filename
        ext = src.suffix.lower()
        target_name = f"{product_number}{view_suffix}{ext}"
        target_path = MEDIA_PENDING_BG_REMOVAL / target_name
        
        # Check for conflicts
        counter = 1
        while target_path.exists():
            self.logger.warning(f"File {target_name} already exists in pending_bg_removal")
            target_path = MEDIA_PENDING_BG_REMOVAL / f"{product_number}{view_suffix}_{counter}{ext}"
            counter += 1
            
            if counter > 100:
                move_to_errors(src, "Too many duplicate files")
                return False
        
        try:
            # Get username from file BEFORE moving (captures original Samba uploader)
            username = AuditLog.get_samba_username(src)
            
            # Create product directory and initial audit entry
            product_dir = get_product_dir(product_number)
            product_dir.mkdir(parents=True, exist_ok=True)
            
            AuditLog.create_or_update(
                product_number=product_number,
                action="initial_upload",
                user_id=username,
                source_file=src,
                details=f"File uploaded: {src.name}"
            )
            
            # Move to pending
            safe_move(src, target_path)
            
            self.logger.info(
                f"Moved to pending",
                product_number=product_number,
                user_id=username,
                source_file=src.name,
                target_file=target_path.name
            )
            
            return True
            
        except Exception as e:
            move_to_errors(src, f"Failed to process: {e}")
            return False


def main():
    """Process all files in inbox."""
    pipeline = RenameIncomingPipeline()
    stats = pipeline.run()
    return stats.failed == 0  # Return True if no failures


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
