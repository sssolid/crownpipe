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
from typing import Any, Iterable, Optional

import yaml

from crownpipe.common.exceptions import FileProcessingError
from crownpipe.common.paths import (
    MEDIA_PRODUCTS,
    ensure_media_dirs,
    get_product_formats_dir,
)
from crownpipe.common.pipeline import BasePipeline
from crownpipe.media.audit import AuditLog
from crownpipe.media.fileutils import is_image_file


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


class FormatPipeline(BasePipeline):
    """Pipeline for generating product format images."""
    
    def __init__(self):
        super().__init__(pipeline_name='format_pipeline')
        ensure_media_dirs()
        self.convert_bin = self.settings.media.imagemagick_convert_bin
        self.specs_path = Path(__file__).resolve().parent / "output_specs.yaml"
        self.specs = self.load_specs()
        self.logger.info(f"Loaded {len(self.specs)} format specifications")
    
    def get_items(self) -> Iterable[Path]:
        """Get product directories that need formatting."""
        if not MEDIA_PRODUCTS.exists():
            return []
        
        return [d for d in MEDIA_PRODUCTS.iterdir() if d.is_dir()]
    
    def should_skip_item(self, product_dir: Path) -> bool:
        """Skip if product has no source files or is already formatted."""
        source_dir = product_dir / "source"
        if not source_dir.exists():
            return True
        
        source_files = [f for f in source_dir.iterdir() if is_image_file(f)]
        if not source_files:
            return True
        
        # Skip if already formatted (unless force mode)
        formats_dir = get_product_formats_dir(product_dir.name)
        if formats_dir.exists():
            existing_formats = list(formats_dir.rglob("*.*"))
            if len(existing_formats) > 0:
                self.logger.debug(
                    f"Skipping - already has {len(existing_formats)} formats",
                    product_number=product_dir.name
                )
                return True
        
        return False
    
    def load_specs(self) -> list[FormatSpec]:
        """Load all format specifications from YAML."""
        with open(self.specs_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        def tuple_or_none(v):
            if v is None:
                return None
            return tuple(int(x) for x in v)
        
        specs = []
        for raw in data:
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
            
            spec = FormatSpec(
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
            specs.append(spec)
        
        return specs
    
    def run_convert(self, args: list[str], input_bytes: bytes | None = None) -> bytes:
        """Run ImageMagick convert command."""
        cmd = [self.convert_bin] + args
        try:
            result = subprocess.run(
                cmd,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=300
            )
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="ignore")
            raise FileProcessingError(
                f"ImageMagick convert failed: {stderr}",
                context={'cmd': ' '.join(cmd)}
            ) from e
        
        return result.stdout
    
    def load_trimmed_base_png(self, src: Path) -> bytes:
        """Load and normalize source image to PNG."""
        self.logger.debug(f"Loading base PNG", source_file=src.name)
        return self.run_convert([
            str(src),
            "-alpha", "on",
            "-colorspace", "sRGB",
            "-strip",
            "-trim", "+repage",
            "PNG32:-",
        ])
    
    def extension_for_format(self, fmt: str) -> str:
        """Get file extension for format."""
        f = fmt.upper()
        if f == "JPEG":
            return "jpg"
        if f == "TIFF":
            return "tif"
        if f == "PNG":
            return "png"
        raise ValueError(f"Unsupported format: {fmt}")
    
    def exif_args_for(self, product_number: str) -> list[str]:
        """Build EXIF metadata arguments."""
        now = datetime.now(UTC).strftime("%Y:%m:%d %H:%M:%S")
        desc = f"Crown Automotive product image {product_number}"
        keywords = f"Crown Automotive,{product_number},product"
        
        return [
            "-set", "exif:Artist", "Crown Automotive Sales Co., Inc.",
            "-set", "exif:Make", "Crown Automotive Sales Co., Inc.",
            "-set", "exif:Model", product_number,
            "-set", "exif:ImageDescription", desc,
            "-set", "exif:Software", "Crown Automotive Media Pipeline v3",
            "-set", "exif:Copyright", "Copyright (c) Crown Automotive Sales Co., Inc.",
            "-set", "exif:DateTime", now,
            "-set", "exif:XPKeywords", keywords,
        ]
    
    def build_convert_args(self, spec: FormatSpec, product_number: str, out_path: Path) -> list[str]:
        """Build ImageMagick arguments for a format."""
        # Determine background color
        if spec.background is not None:
            bg_color = spec.background
        else:
            bg_color = "none" if spec.mode.upper() == "RGBA" else "white"
        
        args: list[str] = [
            "PNG:-",
            "-colorspace", "sRGB",
            "-strip",
            "-units", "PixelsPerInch",
            "-density", str(spec.dpi),
            "-alpha", "on",
        ]
        
        # Resize longest side
        if spec.resize_longest is not None:
            side = f"{spec.resize_longest}x{spec.resize_longest}"
            args.extend(["-resize", side])
        
        # Exact resize
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
        
        # Handle alpha channel
        if spec.mode.upper() == "RGB":
            flatten_bg = spec.background or "white"
            args.extend([
                "-background", flatten_bg,
                "-alpha", "remove",
                "-alpha", "off",
            ])
        else:
            args.extend(["-colorspace", "sRGB"])
        
        # Add EXIF metadata
        args.extend(self.exif_args_for(product_number))
        
        # Format-specific options
        if spec.fmt.upper() == "JPEG":
            args.extend([
                "-quality", str(self.settings.media.jpeg_quality),
                "-interlace", "JPEG",
            ])
        elif spec.fmt.upper() == "TIFF":
            args.extend([
                "-compress", "LZW",
            ])
        
        # Output path
        args.append(str(out_path))
        return args
    
    def process_item(self, product_dir: Path) -> bool:
        """
        Generate all formats for a product.
        
        Args:
            product_dir: Product directory
            
        Returns:
            True if successful
        """
        product_number = product_dir.name
        source_dir = product_dir / "source"
        
        self.logger.set_context(product_number=product_number)
        
        try:
            # Find all source images
            source_files = [f for f in source_dir.iterdir() if is_image_file(f)]
            if not source_files:
                return False
            
            total_formats = 0
            
            # Process each source file
            for source_file in source_files:
                self.logger.info(f"Formatting", source_file=source_file.name)
                
                try:
                    # Load and normalize base PNG
                    base_png = self.load_trimmed_base_png(source_file)
                except Exception as e:
                    self.logger.error(f"Failed to load {source_file.name}", exc_info=e)
                    continue
                
                # Determine view suffix
                stem = source_file.stem
                if stem != product_number:
                    view_suffix = stem.replace(product_number, "")
                else:
                    view_suffix = ""
                
                # Generate each format
                formats_generated = []
                for spec in self.specs:
                    try:
                        ext = self.extension_for_format(spec.fmt)
                        
                        # Build output path: formats/category/filename
                        category_dir = get_product_formats_dir(product_number) / spec.category
                        category_dir.mkdir(parents=True, exist_ok=True)
                        
                        output_filename = f"{product_number}{view_suffix}_{spec.name}.{ext}"
                        output_path = category_dir / output_filename
                        
                        # Skip if file exists
                        if output_path.exists():
                            continue
                        
                        # Generate format
                        args = self.build_convert_args(spec, product_number, output_path)
                        self.run_convert(args, input_bytes=base_png)
                        
                        self.logger.debug(
                            f"Generated format",
                            format_category=spec.category,
                            format_name=spec.name
                        )
                        
                        formats_generated.append(f"{spec.category}/{spec.name}")
                        
                        # Add to audit
                        AuditLog.add_format(
                            product_number=product_number,
                            format_name=f"{spec.category}/{spec.name}",
                            file_path=output_path
                        )
                        
                    except Exception as e:
                        self.logger.error(
                            f"Failed to generate format",
                            exc_info=e,
                            format_name=spec.name,
                            source_file=source_file.name
                        )
                
                total_formats += len(formats_generated)
            
            if total_formats > 0:
                # Add audit entry for formatting completion
                AuditLog.create_or_update(
                    product_number=product_number,
                    action="formatting_complete",
                    details=f"Generated {total_formats} formats"
                )
                
                self.logger.info(f"Generated {total_formats} formats", product_number=product_number)
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to format product", exc_info=e)
            return False
        finally:
            self.logger.clear_context()


def main():
    """Process all products that need formatting."""
    pipeline = FormatPipeline()
    stats = pipeline.run()
    return stats.failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
