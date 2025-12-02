#!/usr/bin/env python3
"""
Web dashboard for media pipeline.
Displays product status, audit history, and format availability.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import asdict
import io

from flask import Flask, render_template, jsonify, send_file
from PIL import Image

from crownpipe.common.logger import get_logger
from crownpipe.common.paths import (
    MEDIA_PRODUCTS,
    MEDIA_INBOX,
    MEDIA_PENDING_BG_REMOVAL,
    MEDIA_BG_REMOVED,
    MEDIA_BG_REMOVAL_FAILED,
    MEDIA_NAME_CONFLICTS,
    MEDIA_READY_FOR_FORMATTING,
    MEDIA_PRODUCTION,
)
from crownpipe.media.audit import AuditLog

logger = get_logger(__name__)
app = Flask(__name__)


def get_product_info(product_dir: Path) -> dict:
    """
    Get comprehensive info about a product.
    
    Args:
        product_dir: Path to product directory
        
    Returns:
        Dictionary with product information
    """
    product_number = product_dir.name
    
    # Load audit
    audit = AuditLog.load(product_dir)
    
    # Get source files
    source_dir = product_dir / "source"
    source_files = []
    if source_dir.exists():
        source_files = [f.name for f in source_dir.iterdir() if f.is_file()]
    
    # Get format categories and files
    formats_dir = product_dir / "formats"
    formats = {}
    if formats_dir.exists():
        for category_dir in formats_dir.iterdir():
            if category_dir.is_dir():
                files = [f.name for f in category_dir.iterdir() if f.is_file()]
                formats[category_dir.name] = files
    
    # Check production status
    prod_dir = MEDIA_PRODUCTION / product_number
    in_production = prod_dir.exists()
    
    return {
        "product_number": product_number,
        "source_files": source_files,
        "formats": formats,
        "in_production": in_production,
        "audit": asdict(audit) if audit else None,
        "last_modified": product_dir.stat().st_mtime
    }


def get_pipeline_stats() -> dict:
    """
    Get overall pipeline statistics.
    
    Returns:
        Dictionary with pipeline stats
    """
    stats = {
        "inbox": len(list(MEDIA_INBOX.iterdir())) if MEDIA_INBOX.exists() else 0,
        "pending_bg_removal": len(list(MEDIA_PENDING_BG_REMOVAL.iterdir())) if MEDIA_PENDING_BG_REMOVAL.exists() else 0,
        "bg_removed": len(list(MEDIA_BG_REMOVED.iterdir())) if MEDIA_BG_REMOVED.exists() else 0,
        "bg_removal_failed": len(list(MEDIA_BG_REMOVAL_FAILED.iterdir())) if MEDIA_BG_REMOVAL_FAILED.exists() else 0,
        "name_conflicts": len(list(MEDIA_NAME_CONFLICTS.iterdir())) if MEDIA_NAME_CONFLICTS.exists() else 0,
        "ready_for_formatting": len(list(MEDIA_READY_FOR_FORMATTING.iterdir())) if MEDIA_READY_FOR_FORMATTING.exists() else 0,
        "total_products": len(list(MEDIA_PRODUCTS.iterdir())) if MEDIA_PRODUCTS.exists() else 0,
        "in_production": len(list(MEDIA_PRODUCTION.iterdir())) if MEDIA_PRODUCTION.exists() else 0,
    }
    return stats


@app.route('/')
def index():
    """Main dashboard page."""
    stats = get_pipeline_stats()
    return render_template('dashboard.html', stats=stats)


@app.route('/api/stats')
def api_stats():
    """API endpoint for pipeline statistics."""
    return jsonify(get_pipeline_stats())


@app.route('/api/products')
def api_products():
    """API endpoint for product list."""
    if not MEDIA_PRODUCTS.exists():
        return jsonify([])
    
    products = []
    for product_dir in sorted(MEDIA_PRODUCTS.iterdir()):
        if not product_dir.is_dir():
            continue
        try:
            info = get_product_info(product_dir)
            products.append(info)
        except Exception as e:
            logger.error(f"Error loading {product_dir.name}: {e}")
    
    return jsonify(products)


@app.route('/api/product/<product_number>')
def api_product(product_number: str):
    """API endpoint for single product details."""
    product_dir = MEDIA_PRODUCTS / product_number
    if not product_dir.exists():
        return jsonify({"error": "Product not found"}), 404
    
    try:
        info = get_product_info(product_dir)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/review')
def api_review():
    """API endpoint for items needing review."""
    review_items = {
        "bg_removed": [],
        "bg_removal_failed": [],
        "name_conflicts": []
    }
    
    def get_file_info(file_path):
        """Get file info including size and modification time."""
        stat = file_path.stat()
        return {
            "name": file_path.name,
            "size": stat.st_size,
            "modified": stat.st_mtime
        }
    
    if MEDIA_BG_REMOVED.exists():
        review_items["bg_removed"] = [
            get_file_info(f) for f in MEDIA_BG_REMOVED.iterdir() if f.is_file()
        ]
    
    if MEDIA_BG_REMOVAL_FAILED.exists():
        review_items["bg_removal_failed"] = [
            get_file_info(f) for f in MEDIA_BG_REMOVAL_FAILED.iterdir() if f.is_file()
        ]
    
    if MEDIA_NAME_CONFLICTS.exists():
        review_items["name_conflicts"] = [
            get_file_info(f) for f in MEDIA_NAME_CONFLICTS.iterdir() if f.is_file()
        ]
    
    return jsonify(review_items)


@app.route('/image/thumbnail/<path:folder>/<path:filename>')
def serve_thumbnail(folder: str, filename: str):
    """
    Serve a thumbnail version of an image.
    
    Args:
        folder: Which folder (bg_removed, bg_removal_failed, etc)
        filename: Image filename
    """
    try:
        # Map folder names to paths
        folder_map = {
            "bg_removed": MEDIA_BG_REMOVED,
            "bg_removal_failed": MEDIA_BG_REMOVAL_FAILED,
            "name_conflicts": MEDIA_NAME_CONFLICTS,
            "ready_for_formatting": MEDIA_READY_FOR_FORMATTING,
        }
        
        if folder not in folder_map:
            return "Invalid folder", 404
        
        image_path = folder_map[folder] / filename
        if not image_path.exists():
            return "Image not found", 404
        
        # Generate thumbnail
        img = Image.open(image_path)
        img.thumbnail((300, 300), Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary (for JPEG)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # Save to bytes
        img_io = io.BytesIO()
        img.save(img_io, 'JPEG', quality=85)
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/jpeg')
    
    except Exception as e:
        logger.error(f"Error serving thumbnail {folder}/{filename}: {e}")
        return "Error generating thumbnail", 500


@app.route('/image/full/<path:folder>/<path:filename>')
def serve_full_image(folder: str, filename: str):
    """
    Serve a full-size image.
    
    Args:
        folder: Which folder (bg_removed, bg_removal_failed, etc)
        filename: Image filename
    """
    try:
        # Map folder names to paths
        folder_map = {
            "bg_removed": MEDIA_BG_REMOVED,
            "bg_removal_failed": MEDIA_BG_REMOVAL_FAILED,
            "name_conflicts": MEDIA_NAME_CONFLICTS,
            "ready_for_formatting": MEDIA_READY_FOR_FORMATTING,
        }
        
        if folder not in folder_map:
            return "Invalid folder", 404
        
        image_path = folder_map[folder] / filename
        if not image_path.exists():
            return "Image not found", 404
        
        return send_file(image_path)
    
    except Exception as e:
        logger.error(f"Error serving image {folder}/{filename}: {e}")
        return "Error serving image", 500


@app.template_filter('datetime')
def format_datetime(timestamp_str: Optional[str]) -> str:
    """Format ISO timestamp for display."""
    if not timestamp_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp_str


@app.template_filter('timeago')
def timeago(timestamp: float) -> str:
    """Convert Unix timestamp to relative time."""
    try:
        dt = datetime.fromtimestamp(timestamp)
        now = datetime.now()
        diff = now - dt
        
        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds >= 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds >= 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"
    except:
        return "unknown"


def main():
    """Run development server."""
    # Create templates directory if it doesn't exist
    templates_dir = Path(__file__).parent / 'templates'
    templates_dir.mkdir(exist_ok=True)
    
    # Run development server
    app.run(host='0.0.0.0', port=5000, debug=True)


if __name__ == '__main__':
    main()
