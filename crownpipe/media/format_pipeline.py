#!/usr/bin/env python3
"""
Image formatting pipeline.
- Scans product source directories
- Generates all output formats
- Organizes by format type (print/web/thumbnail/transparent)
- Updates audit trail
"""
import subprocess
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional

import yaml

from crownpipe.common.logger import get_logger
from crownpipe.common.paths import (
    MEDIA_PRODUCTS,
    ensure_media_dirs,
    get_product_formats_dir,
)
from crownpipe.media.audit import AuditLog
from crownpipe.media.fileutils import is_image_file, move_to_errors

logger = get_logger(__name__)

CONVERT_BIN = "convert"
SCRIPT_DIR = Path(__file__).resolve().parent
SPECS_PATH = SCRIPT_DIR / "output_specs.yaml"


def run_convert(args, input_bytes: bytes | None = None) -> bytes:
    """Run ImageMagick convert command."""
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


def load_trimmed_base_png(src: Path) -> bytes:
    """
    Load and normalize source image to PNG.
    
    Args:
        src: Source image path
        
    Returns:
        Normalized PNG bytes
    """
    logger.debug(f"Loading base PNG: {src}")
    return run_convert([
        str(src),
        "-alpha", "on",
        "-colorspace", "sRGB",
        "-strip",
        "-trim", "+repage",
        "PNG32:-",
    ])


@dataclass
class FormatSpec:
    """Specification for an output format."""
    name: str
    fmt: str
    dpi: int
    background: Optional[str]
    resize: Optional[tuple[int, int]]
    resize_longest: Optional[int]
    extent: Optional[tuple[int, int]]
    border: tuple[int, int]
    mode: str
    brand_icon: Optional[str]
    icon_offset: tuple[int, int]
    watermark: Optional[str]
    category: str  # print, web, thumbnail, transparent


def parse_spec(raw: dict[str, Any]) -> FormatSpec:
    """Parse format specification from YAML."""
    def tuple_or_none(v):
        if v is None:
            return None
        return tuple(int(x) for x in v)
    
    # Determine category based on name and properties
    name = raw["name"]
    if "original" in name or (raw.get("mode") == "RGBA" and raw["dpi"] >= 300):
        category = "transparent"
    elif raw["dpi"] >= 300:
        category = "print"
    elif any(size in name for size in ["128", "64", "32"]):
        category = "thumbnail"
    else:
        category = "web"
    
    return FormatSpec(
        name=raw["name"],
        fmt=raw["format"],
        dpi=int(raw["dpi"]),
        background=raw.get("background"),
        resize=tuple_or_none(raw.get("resize")),
        resize_longest=int(raw["resize_longest"]) if raw.get("resize_longest") is not None else None,
        extent=tuple_or_none(raw.get("extent")),
        border=tuple_or_none(raw.get("border")) or (0, 0),
        mode=raw.get("mode", "RGB"),
        brand_icon=raw.get("brand_icon"),
        icon_offset=tuple_or_none(raw.get("icon_offset")) or (15, 15),
        watermark=raw.get("watermark"),
        category=category
    )


def load_specs() -> list[FormatSpec]:
    """Load all format specifications from YAML."""
    with open(SPECS_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [parse_spec(item) for item in data]


def exif_args_for(product_number: str) -> list[str]:
    """
    Build EXIF metadata arguments.
    
    Args:
        product_number: Product number for metadata
        
    Returns:
        List of ImageMagick arguments
    """
    now = datetime.now(UTC).strftime("%Y:%m:%d %H:%M:%S")
    desc = f"Crown Automotive product image {product_number}"
    keywords = f"Crown Automotive,{product_number},product"
    
    return [
        "-set", "exif:Artist", "Crown Automotive Sales Co., Inc.",
        "-set", "exif:Make", "Crown Automotive Sales Co., Inc.",
        "-set", "exif:Model", product_number,
        "-set", "exif:ImageDescription", desc,
        "-set", "exif:Software", "Crown Automotive Media Pipeline v2",
        "-set", "exif:Copyright", "Copyright (c) Crown Automotive Sales Co., Inc.",
        "-set", "exif:DateTime", now,
        "-set", "exif:XPKeywords", keywords,
    ]


def extension_for_format(fmt: str) -> str:
    """Get file extension for format."""
    f = fmt.upper()
    if f == "JPEG":
        return "jpg"
    if f == "TIFF":
        return "tif"
    if f == "PNG":
        return "png"
    raise ValueError(f"Unsupported format: {fmt}")


def build_convert_args_for_format(
    spec: FormatSpec,
    product_number: str,
    out_path: Path
) -> list[str]:
    """
    Build ImageMagick arguments for a format.
    
    Args:
        spec: Format specification
        product_number: Product number
        out_path: Output file path
        
    Returns:
        List of convert arguments
    """
    # Determine background color
    if spec.background is not None:
        bg_color = spec.background
    else:
        bg_color = "none" if spec.mode.upper() == "RGBA" else "white"
    
    args: list[str] = [
        "PNG:-",  # Read from stdin
        "-colorspace", "sRGB",
        "-strip",
        "-units", "PixelsPerInch",
        "-density", str(spec.dpi),
        "-alpha", "on",
    ]
    
    # Resize longest side if specified
    if spec.resize_longest is not None:
        side = f"{spec.resize_longest}x{spec.resize_longest}"
        args.extend(["-resize", side])
    
    # Exact resize if specified
    if spec.resize is not None:
        w, h = spec.resize
        geom = f"{w}x{h}"
        args.extend(["-resize", geom])
    
    # Extent (canvas size with centering)
    if spec.extent is not None:
        ew, eh = spec.extent
        extent_geom = f"{ew}x{eh}"
        args.extend([
            "-background", bg_color,
            "-gravity", "center",
            "-extent", extent_geom,
        ])
    
    # Border
    bx, by = spec.border
    if bx > 0 or by > 0:
        border_geom = f"{bx}x{by}"
        args.extend([
            "-bordercolor", bg_color,
            "-border", border_geom,
        ])
    
    # Brand icon (top-left)
    if spec.brand_icon:
        icon_path = SCRIPT_DIR / spec.brand_icon
        if icon_path.exists():
            dx, dy = spec.icon_offset
            geom = f"+{dx}+{dy}"
            args.extend([
                str(icon_path),
                "-gravity", "northwest",
                "-geometry", geom,
                "-composite",
            ])
    
    # Watermark (bottom-right)
    if spec.watermark:
        wm_path = SCRIPT_DIR / spec.watermark
        if wm_path.exists():
            dx, dy = spec.icon_offset
            geom = f"+{dx}+{dy}"
            args.extend([
                str(wm_path),
                "-gravity", "southeast",
                "-geometry", geom,
                "-composite",
            ])
    
    # Handle alpha channel based on mode
    if spec.mode.upper() == "RGB":
        # Flatten alpha against background
        flatten_bg = spec.background or "white"
        args.extend([
            "-background", flatten_bg,
            "-alpha", "remove",
            "-alpha", "off",
        ])
    else:
        # Keep RGBA
        args.extend(["-colorspace", "sRGB"])
    
    # Add EXIF metadata
    args.extend(exif_args_for(product_number))
    
    # Format-specific options
    if spec.fmt.upper() == "JPEG":
        args.extend([
            "-quality", "90",
            "-interlace", "JPEG",
        ])
    elif spec.fmt.upper() == "TIFF":
        args.extend([
            "-compress", "LZW",
        ])
    
    # Output path
    args.append(str(out_path))
    return args


def format_product(product_dir: Path, specs: list[FormatSpec], force: bool = False):
    """
    Generate all formats for a product.
    
    Args:
        product_dir: Product directory
        specs: List of format specifications
        force: If True, regenerate even if formats exist
    """
    product_number = product_dir.name
    source_dir = product_dir / "source"
    
    if not source_dir.exists():
        logger.debug(f"No source directory for {product_number}")
        return
    
    # Find all source images
    source_files = [f for f in source_dir.iterdir() if is_image_file(f)]
    if not source_files:
        logger.debug(f"No source files for {product_number}")
        return
    
    # Check if already formatted (unless forcing)
    if not force:
        formats_dir = get_product_formats_dir(product_number)
        if formats_dir.exists():
            # Count existing format files
            existing_formats = list(formats_dir.rglob("*.*"))
            if len(existing_formats) > 0:
                logger.debug(f"Skipping {product_number} - already has {len(existing_formats)} formats")
                return
    
    # Process each source file (handles multiple views)
    for source_file in source_files:
        logger.info(f"Formatting {product_number}/{source_file.name}")
        
        try:
            # Load and normalize base PNG
            base_png = load_trimmed_base_png(source_file)
        except Exception as e:
            logger.error(f"Failed to load {source_file}: {e}")
            continue
        
        # Determine view suffix (e.g., "_1", "_2")
        stem = source_file.stem
        if stem != product_number:
            # Extract view suffix
            view_suffix = stem.replace(product_number, "")
        else:
            view_suffix = ""
        
        # Generate each format
        formats_generated = []
        for spec in specs:
            try:
                ext = extension_for_format(spec.fmt)
                
                # Build output path: formats/category/filename
                category_dir = get_product_formats_dir(product_number) / spec.category
                category_dir.mkdir(parents=True, exist_ok=True)
                
                output_filename = f"{product_number}{view_suffix}_{spec.name}.{ext}"
                output_path = category_dir / output_filename
                
                # Skip if file exists and not forcing
                if not force and output_path.exists():
                    continue
                
                # Generate format
                args = build_convert_args_for_format(spec, product_number, output_path)
                run_convert(args, input_bytes=base_png)
                
                logger.info(f"  Generated: {spec.category}/{output_filename}")
                formats_generated.append(f"{spec.category}/{spec.name}")
                
            except Exception as e:
                logger.error(f"Failed to generate {spec.name} for {source_file}: {e}")
        
        # Update audit log with formats generated
        for format_name in set(formats_generated):
            AuditLog.add_format(product_dir, format_name)
        
        # Add audit entry for formatting completion
        if formats_generated:
            AuditLog.create_or_update(
                product_dir,
                product_number,
                "formatting_complete",
                details=f"Generated {len(formats_generated)} formats from {source_file.name}"
            )


def main():
    """Process all products that need formatting."""
    ensure_media_dirs()
    
    # Load format specifications
    specs = load_specs()
    logger.info(f"Loaded {len(specs)} format specifications")
    
    # Process each product directory
    if not MEDIA_PRODUCTS.exists():
        logger.warning("Products directory does not exist")
        return
    
    for product_dir in MEDIA_PRODUCTS.iterdir():
        if not product_dir.is_dir():
            continue
        
        try:
            format_product(product_dir, specs)
        except Exception as e:
            logger.error(f"Error formatting {product_dir.name}: {e}")


if __name__ == "__main__":
    main()
