#!/usr/bin/env python3
"""
Process human-approved images from ready_for_formatting.

Creates the product directory structure and prepares for formatting.
Only runs on files that humans have manually moved to ready_for_formatting.
"""
from pathlib import Path
from typing import Iterable

from crownpipe.common.paths import (
    MEDIA_READY_FOR_FORMATTING,
    ensure_media_dirs,
    get_product_dir,
    get_product_source_dir,
)
from crownpipe.common.pipeline import FileProcessingPipeline
from crownpipe.media.audit import AuditLog
from crownpipe.media.fileutils import (
    extract_product_number,
    get_view_suffix,
    is_image_file,
    move_to_errors,
    safe_move,
)


class PrepareFormattingPipeline(FileProcessingPipeline):
    """Pipeline for preparing human-approved images for formatting."""
    
    def __init__(self):
        super().__init__(source_dir=MEDIA_READY_FOR_FORMATTING, pipeline_name='prepare_formatting')
        ensure_media_dirs()
    
    def get_items(self) -> Iterable[Path]:
        """Get image files from ready_for_formatting."""
        if not self.source_dir.exists():
            return []
        
        return [f for f in self.source_dir.iterdir() if f.is_file() and is_image_file(f)]
    
    def process_item(self, src: Path) -> bool:
        """
        Move human-approved image to product source directory.
        Creates audit log and prepares for format generation.
        
        Args:
            src: Source file in ready_for_formatting
            
        Returns:
            True if successful
        """
        self.logger.info(f"Preparing for formatting", source_file=src.name)
        
        # Extract product info
        product_number = extract_product_number(src.name)
        if not product_number:
            move_to_errors(src, "Could not extract product number")
            return False
        
        view_suffix = get_view_suffix(src.name)
        
        self.logger.set_context(product_number=product_number)
        
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
            self.logger.info(
                "Moved to products",
                product_number=product_number,
                target_path=str(target_path)
            )
            
            # Create/update audit log
            AuditLog.create_or_update(
                product_number=product_number,
                action="human_approved",
                user_id="system",
                details=f"Human reviewed and approved {src.name} for formatting"
            )
            
            self.logger.info(f"Ready for format generation", product_number=product_number)
            return True
            
        except Exception as e:
            move_to_errors(src, f"Failed to prepare for formatting: {e}")
            return False
        finally:
            self.logger.clear_context()


def main():
    """Process all files in ready_for_formatting directory."""
    pipeline = PrepareFormattingPipeline()
    stats = pipeline.run()
    
    if stats.successful > 0:
        pipeline.logger.info(f"Prepared {stats.successful} images for formatting")
    
    return stats.failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
