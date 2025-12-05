#!/usr/bin/env python3
"""
Background removal pipeline.

- Processes files from pending_bg_removal
- Removes background using rembg
- Saves to review directory for human inspection
"""
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable

from rembg import remove

from crownpipe.common.exceptions import FileProcessingError
from crownpipe.common.paths import (
    MEDIA_ARCHIVE,
    MEDIA_BG_REMOVED,
    MEDIA_BG_REMOVAL_FAILED,
    MEDIA_PENDING_BG_REMOVAL,
    ensure_media_dirs,
)
from crownpipe.common.pipeline import FileProcessingPipeline
from crownpipe.media.fileutils import (
    extract_product_number,
    get_view_suffix,
    is_image_file,
    move_to_errors,
    safe_move,
    wait_for_complete_file,
)


class BackgroundRemovalPipeline(FileProcessingPipeline):
    """Pipeline for background removal processing."""
    
    def __init__(self):
        super().__init__(source_dir=MEDIA_PENDING_BG_REMOVAL, pipeline_name='bgremove')
        ensure_media_dirs()
        self.convert_bin = self.settings.media.imagemagick_convert_bin
    
    def get_items(self) -> Iterable[Path]:
        """Get image files from pending_bg_removal."""
        if not self.source_dir.exists():
            return []
        
        return [f for f in self.source_dir.iterdir() if f.is_file() and is_image_file(f)]
    
    def run_convert(self, args: list[str], input_bytes: bytes | None = None) -> bytes:
        """
        Run ImageMagick 'convert' with the given argument list.
        
        Args:
            args: List of arguments (excluding binary name)
            input_bytes: Optional input data via stdin
            
        Returns:
            stdout bytes
            
        Raises:
            FileProcessingError: If convert fails
        """
        cmd = [self.convert_bin] + args
        try:
            result = subprocess.run(
                cmd,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=self.settings.media.bgremove_timeout_seconds
            )
        except subprocess.TimeoutExpired as e:
            raise FileProcessingError(
                "ImageMagick convert timeout",
                context={'cmd': ' '.join(cmd), 'timeout': self.settings.media.bgremove_timeout_seconds}
            ) from e
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="ignore")
            raise FileProcessingError(
                f"ImageMagick convert failed: {stderr}",
                context={'cmd': ' '.join(cmd)}
            ) from e
        
        return result.stdout
    
    def source_to_png_bytes(self, src: Path) -> bytes:
        """
        Convert any input format to standardized PNG.
        
        Args:
            src: Source image path
            
        Returns:
            PNG bytes (RGBA, 8-bit, sRGB)
        """
        self.logger.debug(f"Normalizing to PNG", source_file=src.name)
        return self.run_convert([
            str(src),
            "-alpha", "on",
            "-colorspace", "sRGB",
            "-strip",
            "PNG32:-",  # RGBA, 8-bit, written to stdout
        ])
    
    def trim_png_bytes(self, png_bytes: bytes) -> bytes:
        """
        Trim transparent borders from PNG.
        
        Args:
            png_bytes: Input PNG bytes
            
        Returns:
            Trimmed PNG bytes
        """
        self.logger.debug("Trimming PNG")
        return self.run_convert([
            "PNG:-",
            "-alpha", "on",
            "-colorspace", "sRGB",
            "-trim", "+repage",
            "PNG32:-",
        ], input_bytes=png_bytes)
    
    def process_item(self, src: Path) -> bool:
        """
        Process a single file through background removal.
        ALL results (success or failure) go to review folder for human inspection.
        
        Args:
            src: Source file in pending_bg_removal
            
        Returns:
            True if successful
        """
        with self.logger.log_execution('background_removal', source_file=src.name):
            # Wait for file stability
            if not wait_for_complete_file(src):
                move_to_errors(src, "File never stabilized before bg removal")
                return False
            
            # Extract product info
            product_number = extract_product_number(src.name)
            if not product_number:
                move_to_errors(src, "Could not extract product number")
                return False
            
            view_suffix = get_view_suffix(src.name)
            
            self.logger.set_context(product_number=product_number)
            
            bg_removed_success = False
            output_png = None
            
            try:
                # Step 1: Normalize to PNG
                base_png = self.source_to_png_bytes(src)
                
                # Step 2: Background removal
                self.logger.info("Running rembg", product_number=product_number)
                bg_removed_png = remove(base_png)
                
                # Step 3: Trim
                trimmed_png = self.trim_png_bytes(bg_removed_png)
                
                output_png = trimmed_png
                bg_removed_success = True
                
            except Exception as e:
                self.logger.error(
                    f"Background removal failed",
                    exc_info=e,
                    product_number=product_number
                )
                # On failure, normalize the original for manual editing
                try:
                    output_png = self.source_to_png_bytes(src)
                except Exception as e2:
                    move_to_errors(src, f"BG removal failed and couldn't normalize: {e}, {e2}")
                    return False
            
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
                
                # Build output filename
                output_name = f"{product_number}{view_suffix}.png"
                output_path = dest_dir / output_name
                
                # Write the processed image
                with open(output_path, "wb") as f:
                    f.write(output_png)
                
                self.logger.info(
                    f"Saved to review ({status})",
                    product_number=product_number,
                    output_path=str(output_path)
                )
                
                # Archive the original file
                year_month = datetime.now().strftime("%Y-%m")
                archive_dir = MEDIA_ARCHIVE / year_month / product_number
                archive_dir.mkdir(parents=True, exist_ok=True)
                archive_path = archive_dir / src.name
                
                safe_move(src, archive_path)
                self.logger.debug(f"Archived original", archive_path=str(archive_path))
                
                return True
                
            except Exception as e:
                move_to_errors(src, f"Failed to save to review folder: {e}")
                return False
            finally:
                self.logger.clear_context()


def main():
    """Process all files pending background removal."""
    pipeline = BackgroundRemovalPipeline()
    stats = pipeline.run()
    return stats.failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
