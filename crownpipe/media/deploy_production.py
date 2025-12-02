#!/usr/bin/env python3
"""
Prepare products for production deployment.
- Copies formatted products to production directory
- Maintains product-centric structure
- Updates audit logs
"""
import shutil
from pathlib import Path

from crownpipe.common.logger import get_logger
from crownpipe.common.paths import (
    MEDIA_PRODUCTS,
    MEDIA_PRODUCTION,
    ensure_media_dirs,
)
from crownpipe.media.audit import AuditLog

logger = get_logger(__name__)


def sync_product_to_production(product_dir: Path):
    """
    Sync a product's formatted outputs to production.
    
    Args:
        product_dir: Product directory in products/
    """
    product_number = product_dir.name
    formats_dir = product_dir / "formats"
    
    if not formats_dir.exists():
        logger.debug(f"No formats directory for {product_number}")
        return
    
    # Check if there are any formats to sync
    format_files = list(formats_dir.rglob("*.*"))
    if not format_files:
        logger.debug(f"No format files for {product_number}")
        return
    
    logger.info(f"Syncing {product_number} to production ({len(format_files)} files)")
    
    # Create production directory for this product
    prod_dir = MEDIA_PRODUCTION / product_number
    prod_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy all formatted files maintaining structure
    synced_count = 0
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
        except Exception as e:
            logger.error(f"Failed to copy {src_file} to {dest_file}: {e}")
    
    logger.info(f"  Synced {synced_count} files to production/{product_number}")
    
    # Update audit log
    AuditLog.update_production_sync(product_dir)


def clean_orphaned_production():
    """
    Remove products from production that no longer exist in products/.
    This keeps production clean if products are removed/archived.
    """
    if not MEDIA_PRODUCTION.exists():
        return
    
    for prod_dir in MEDIA_PRODUCTION.iterdir():
        if not prod_dir.is_dir():
            continue
        
        product_number = prod_dir.name
        source_dir = MEDIA_PRODUCTS / product_number
        
        if not source_dir.exists():
            logger.info(f"Removing orphaned production directory: {product_number}")
            try:
                shutil.rmtree(prod_dir)
            except Exception as e:
                logger.error(f"Failed to remove {prod_dir}: {e}")


def main():
    """Sync all products to production."""
    ensure_media_dirs()
    
    if not MEDIA_PRODUCTS.exists():
        logger.warning("Products directory does not exist")
        return
    
    # Sync all products
    product_count = 0
    for product_dir in MEDIA_PRODUCTS.iterdir():
        if not product_dir.is_dir():
            continue
        
        try:
            sync_product_to_production(product_dir)
            product_count += 1
        except Exception as e:
            logger.error(f"Error syncing {product_dir.name}: {e}")
    
    logger.info(f"Processed {product_count} products")
    
    # Clean up orphaned production directories
    clean_orphaned_production()


if __name__ == "__main__":
    main()
