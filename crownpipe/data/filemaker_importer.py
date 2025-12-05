#!/usr/bin/env python3
"""
FileMaker data import pipeline.

Scans backup directory for CSV exports, validates headers,
and imports into PostgreSQL staging tables.
"""
import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterable, List, Set, Tuple

from crownpipe.common.db import get_conn
from crownpipe.common.exceptions import DataPipelineError, ValidationError
from crownpipe.common.paths import DATA_BACKUPS, DATA_LOG_FILE, ensure_data_dirs
from crownpipe.common.pipeline import FileProcessingPipeline

# Expected CSV headers
EXPECTED_HEADERS = [
    "number", "upc", "other_number", "date_modified", "active",
    "toggle_adam", "toggle_select", "brand", "group", "country",
    "description", "category", "sub_category", "tertiary_category",
    "sold_as", "packaging", "additional_shipping", "box", "construction",
    "color", "texture", "hardware", "quantity_required", "hazardous",
    "universal", "application", "notes", "csv_vehicle_model",
    "vehicle_model", "axle", "engine", "transmission", "transfer_case",
    "make", "lhd_rhd", "door", "front_rear", "left_right", "upper_lower",
    "inner_outer", "rt_offroad_bullet_1", "rt_offroad_bullet_2",
    "rt_offroad_bullet_3", "rt_offroad_bullet_4", "rt_offroad_bullet_5",
    "rt_offroad_ad_copy"
]

EXPECTED_SET = set(EXPECTED_HEADERS)

OPTIONAL_HEADERS = {
    "additional_shipping",
}

HEADER_ALIASES = {
    # Example: "veh_model": "vehicle_model",
}

FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_Filemaker-Dump\.csv$")


class FileMakerImportPipeline(FileProcessingPipeline):
    """Pipeline for importing FileMaker CSV exports."""
    
    def __init__(self, dry_run: bool = True):
        super().__init__(source_dir=DATA_BACKUPS, pipeline_name='filemaker_import')
        self.dry_run = dry_run
        ensure_data_dirs()
        self.existing_files = self._get_existing_files()
        
        self.logger.info(f"Dry run: {dry_run}")
        self.logger.info(f"Already imported: {len(self.existing_files)} files")
    
    def _get_existing_files(self) -> Set[str]:
        """Get set of filenames already imported."""
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Ensure staging schema exists
                    cur.execute("CREATE SCHEMA IF NOT EXISTS staging;")
                    
                    # Ensure raw_file table exists
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS staging.raw_file (
                            id SERIAL PRIMARY KEY,
                            file_name TEXT NOT NULL,
                            file_date DATE NOT NULL,
                            imported_at TIMESTAMPTZ DEFAULT now(),
                            row_count INTEGER
                        );
                    """)
                    conn.commit()
                    
                    cur.execute("SELECT file_name FROM staging.raw_file;")
                    return {r[0] for r in cur.fetchall()}
        except Exception as e:
            self.logger.warning(f"Could not get existing files: {e}")
            return set()
    
    def get_items(self) -> Iterable[Path]:
        """Get CSV files from backup directory."""
        if not self.source_dir.exists():
            return []
        
        return [f for f in self.source_dir.glob("*.csv")]
    
    def should_skip_item(self, file_path: Path) -> bool:
        """Skip if already imported."""
        return file_path.name in self.existing_files
    
    def extract_date_from_filename(self, name: str) -> str | None:
        """Extract date from filename (YYYY-MM-DD_Filemaker-Dump.csv)."""
        m = FILENAME_RE.match(name)
        return m.group(1) if m else None
    
    def read_headers(self, file_path: Path) -> List[str]:
        """Read CSV headers from file."""
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            headers = next(reader)
        return [h.strip() for h in headers]
    
    def build_header_mapping(self, raw_headers: List[str]) -> Tuple[dict, List[str], List[str]]:
        """
        Build mapping from raw headers to canonical names.
        
        Returns:
            (mapping dict, missing required headers, extra headers)
        """
        mapping = {}
        seen = set()
        extra = []

        for raw in raw_headers:
            key = raw.lower().strip()
            if key in EXPECTED_SET:
                canonical = key
            elif key in HEADER_ALIASES:
                canonical = HEADER_ALIASES[key]
            else:
                extra.append(raw)
                continue

            mapping[raw] = canonical
            seen.add(canonical)

        missing = sorted(EXPECTED_SET - seen)
        return mapping, missing, sorted(extra)
    
    def validate_file(self, file_path: Path) -> Tuple[bool, str, str | None, dict | None]:
        """
        Validate a CSV file.
        
        Returns:
            (is_valid, reason, file_date, header_mapping)
        """
        # Check filename format
        file_date = self.extract_date_from_filename(file_path.name)
        if not file_date:
            return False, "Invalid filename format", None, None
        
        # Check headers
        try:
            raw_headers = self.read_headers(file_path)
        except Exception as e:
            return False, f"Failed to read headers: {e}", None, None
        
        mapping, missing, extra = self.build_header_mapping(raw_headers)
        
        # Check for real missing headers (excluding optional)
        real_missing = [m for m in missing if m not in OPTIONAL_HEADERS]
        
        if real_missing:
            return False, f"Missing required headers: {real_missing}", file_date, None
        
        if extra:
            self.logger.warning(f"Extra headers in {file_path.name}: {extra}")
        
        return True, "Valid", file_date, mapping
    
    def process_item(self, file_path: Path) -> bool:
        """
        Import a CSV file into the database.
        
        Args:
            file_path: Path to CSV file
            
        Returns:
            True if successful
        """
        fname = file_path.name
        
        self.logger.info(f"Processing {fname}")
        
        # Validate file
        is_valid, reason, file_date, mapping = self.validate_file(file_path)
        
        if not is_valid:
            self.logger.error(f"Validation failed: {reason}", file_name=fname)
            return False
        
        if self.dry_run:
            self.logger.info(f"Would import {fname} (dry run)", file_date=file_date)
            return True
        
        # Import file
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("BEGIN;")
                    
                    # Create file entry
                    cur.execute("""
                        INSERT INTO staging.raw_file (file_name, file_date)
                        VALUES (%s, %s)
                        RETURNING id;
                    """, (fname, file_date))
                    file_id = cur.fetchone()[0]
                    
                    # Import rows
                    row_count = 0
                    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Ensure raw_row table exists
                            cur.execute("""
                                CREATE TABLE IF NOT EXISTS staging.raw_row (
                                    id BIGSERIAL PRIMARY KEY,
                                    file_id INTEGER REFERENCES staging.raw_file(id) ON DELETE CASCADE,
                                    row_data JSONB NOT NULL
                                );
                            """)
                            
                            cur.execute("""
                                INSERT INTO staging.raw_row (file_id, row_data)
                                VALUES (%s, %s)
                            """, (file_id, json.dumps(row)))
                            row_count += 1
                    
                    # Update row count
                    cur.execute("""
                        UPDATE staging.raw_file SET row_count = %s WHERE id = %s;
                    """, (row_count, file_id))
                    
                    cur.execute("COMMIT;")
                    
                    self.logger.info(
                        f"Imported {row_count} rows",
                        file_name=fname,
                        file_date=file_date,
                        row_count=row_count
                    )
                    
                    return True
                    
        except Exception as e:
            self.logger.error(
                f"Import failed",
                exc_info=e,
                file_name=fname
            )
            return False


def main():
    """Run FileMaker import pipeline."""
    # Check command line args
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] in ("--apply", "--import"):
        dry_run = False
    
    pipeline = FileMakerImportPipeline(dry_run=dry_run)
    stats = pipeline.run()
    
    # Write summary report
    with open(DATA_LOG_FILE, "w", encoding="utf-8") as log:
        log.write("FileMaker Import Summary\n")
        log.write("=" * 50 + "\n\n")
        log.write(f"Total files processed: {stats.total_items}\n")
        log.write(f"Successfully imported: {stats.successful}\n")
        log.write(f"Failed: {stats.failed}\n")
        log.write(f"Skipped (already imported): {stats.skipped}\n")
        log.write(f"Dry run: {dry_run}\n\n")
        
        if stats.errors:
            log.write("Errors by type:\n")
            for error_type, count in stats.errors.items():
                log.write(f"  {error_type}: {count}\n")
    
    pipeline.logger.info(f"Report written to {DATA_LOG_FILE}")
    
    return stats.failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
