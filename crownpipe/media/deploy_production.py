#!/usr/bin/env python3
"""
Prepare products for production deployment.

- Copies formatted products to production directory
- Maintains product-centric structure
- Updates audit logs
"""
import shutil
from pathlib import Path
from typing import Iterable

from crownpipe.common.paths import (
    MEDIA_PRODUCTS,
    MEDIA_PRODUCTION,
    ensure_media_dirs,
)
from crownpipe.common.pipeline import BasePipeline
from crownpipe.media.audit import AuditLog


class DeployProductionPipeline(BasePipeline):
    """Pipeline for deploying products to production."""
    
    def __init__(self):
        super().__init__(pipeline_name='deploy_production')
        ensure_media_dirs()
    
    def get_items(self) -> Iterable[Path]:
        """Get product directories."""
        if not MEDIA_PRODUCTS.exists():
            return []
        
        return [d for d in MEDIA_PRODUCTS.iterdir() if d.is_dir()]
    
    def should_skip_item(self, product_dir: Path) -> bool:
        """Skip if product has no formats to sync."""
        formats_dir = product_dir / "formats"
        if not formats_dir.exists():
            return True
        
        format_files = list(formats_dir.rglob("*.*"))
        if not format_files:
            return True
        
        return False
    
    def process_item(self, product_dir: Path) -> bool:
        """
        Sync a product's formatted outputs to production.
        
        Args:
            product_dir: Product directory in products/
            
        Returns:
            True if successful
        """
        product_number = product_dir.name
        formats_dir = product_dir / "formats"
        
        self.logger.set_context(product_number=product_number)
        
        try:
            # Get all format files
            format_files = list(formats_dir.rglob("*.*"))
            
            self.logger.info(f"Syncing to production ({len(format_files)} files)")
            
            # Create production directory for this product
            prod_dir = MEDIA_PRODUCTION / product_number
            prod_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy all formatted files maintaining structure
            synced_count = 0
            total_bytes = 0
            
            for src_file in format_files:
                if not src_file.is_file():
                    continue
                
                # Get relative path from formats dir
                rel_path = src_file.relative_to(formats_dir)
                dest_file = prod_dir / rel_path
                
                # Create parent directories
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                try:
                    shutil.copy2(src_file, dest_file)
                    synced_count += 1
                    total_bytes += src_file.stat().st_size
                except Exception as e:
                    self.logger.error(
                        f"Failed to copy file",
                        exc_info=e,
                        src=str(src_file),
                        dest=str(dest_file)
                    )
            
            self.logger.info(
                f"Synced {synced_count} files",
                product_number=product_number,
                files_synced=synced_count,
                total_mb=total_bytes / (1024 * 1024)
            )
            
            # Update audit log
            AuditLog.update_production_sync(product_number, synced_count, total_bytes)
            
            return synced_count > 0
            
        except Exception as e:
            self.logger.error(f"Failed to sync product", exc_info=e)
            return False
        finally:
            self.logger.clear_context()
    
    def clean_orphaned_production(self):
        """Remove products from production that no longer exist in products/."""
        if not MEDIA_PRODUCTION.exists():
            return
        
        for prod_dir in MEDIA_PRODUCTION.iterdir():
            if not prod_dir.is_dir():
                continue
            
            product_number = prod_dir.name
            source_dir = MEDIA_PRODUCTS / product_number
            
            if not source_dir.exists():
                self.logger.info(f"Removing orphaned production directory: {product_number}")
                try:
                    shutil.rmtree(prod_dir)
                except Exception as e:
                    self.logger.error(
                        f"Failed to remove orphaned directory",
                        exc_info=e,
                        product_number=product_number
                    )
    
    def run(self):
        """Run pipeline and clean orphaned directories."""
        stats = super().run()
        
        # Clean up orphaned production directories
        self.logger.info("Cleaning orphaned production directories")
        self.clean_orphaned_production()
        
        return stats


def main():
    """Sync all products to production."""
    pipeline = DeployProductionPipeline()
    stats = pipeline.run()
    return stats.failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
