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
from typing import List, Tuple, Set

from crownpipe.common.db import get_conn
from crownpipe.common.logger import get_logger
from crownpipe.common.paths import DATA_BACKUPS, DATA_LOG_FILE, ensure_data_dirs

logger = get_logger(__name__)

DEFAULT_DRY_RUN = True  # overridden by --apply

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
    # Example:
    # "veh_model": "vehicle_model",
}

FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_Filemaker-Dump\.csv$")


def extract_date_from_filename(name: str) -> str | None:
    """
    Extract date from filename.
    
    Args:
        name: Filename to parse
        
    Returns:
        Date string (YYYY-MM-DD) or None if invalid
    """
    m = FILENAME_RE.match(name)
    return m.group(1) if m else None


def read_headers(file_path: Path) -> List[str]:
    """
    Read CSV headers from file.
    
    Args:
        file_path: Path to CSV file
        
    Returns:
        List of header names
    """
    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)
    return [h.strip() for h in headers]


def build_header_mapping(raw_headers: List[str]) -> Tuple[dict, List[str], List[str]]:
    """
    Build mapping from raw headers to canonical names.
    
    Args:
        raw_headers: Raw header names from CSV
        
    Returns:
        Tuple of (mapping dict, missing required headers, extra headers)
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


def get_existing_files(cur) -> Set[str]:
    """
    Get set of filenames already imported.
    
    Args:
        cur: Database cursor
        
    Returns:
        Set of filenames
    """
    cur.execute("SELECT file_name FROM staging.raw_file;")
    return {r[0] for r in cur.fetchall()}


def main():
    """Main import pipeline."""
    dry_run = DEFAULT_DRY_RUN
    if len(sys.argv) > 1 and sys.argv[1] in ("--apply", "--import"):
        dry_run = False

    ensure_data_dirs()

    logger.info(f"Scanning {DATA_BACKUPS}")
    files = sorted(DATA_BACKUPS.glob("*.csv"))
    logger.info(f"Found {len(files)} files")
    logger.info(f"Dry-run: {dry_run}")

    with get_conn() as conn:
        with conn.cursor() as cur:
            existing = get_existing_files(cur)

    valid_files = []
    problem_files = []
    invalid_names = []
    skipped = []

    for file_path in files:
        fname = file_path.name

        if fname in existing:
            skipped.append(fname)
            continue

        file_date = extract_date_from_filename(fname)
        if not file_date:
            invalid_names.append(fname)
            continue

        try:
            raw_headers = read_headers(file_path)
        except Exception as e:
            problem_files.append((fname, "failed to read headers", [], [str(e)]))
            continue

        mapping, missing, extra = build_header_mapping(raw_headers)

        real_missing = [m for m in missing if m not in OPTIONAL_HEADERS]

        if real_missing or extra:
            problem_files.append((fname, "header mismatch", real_missing, extra))
            continue

        valid_files.append((fname, file_date, mapping))

    # Write report
    with open(DATA_LOG_FILE, "w", encoding="utf-8") as log:
        log.write("FileMaker Import Summary\n")
        log.write("========================\n\n")
        log.write(f"Valid files: {len(valid_files)}\n")
        log.write(f"Invalid names: {len(invalid_names)}\n")
        log.write(f"Header problems: {len(problem_files)}\n")
        log.write(f"Skipped (already imported): {len(skipped)}\n\n")

        for fname, reason, missing, extra in problem_files:
            log.write(f"FILE: {fname}\n  {reason}\n")
            if missing:
                log.write(f"  missing required: {missing}\n")
            if extra:
                log.write(f"  extra: {extra}\n")
            log.write("\n")

    logger.info(f"Validation report written to {DATA_LOG_FILE}")

    if dry_run:
        logger.info("Dry run complete - no data imported")
        return

    # Import valid files
    with get_conn() as conn:
        with conn.cursor() as cur:
            for fname, file_date, mapping in valid_files:
                file_path = DATA_BACKUPS / fname
                logger.info(f"Importing: {fname}")

                try:
                    cur.execute("BEGIN;")

                    cur.execute(
                        """
                        INSERT INTO staging.raw_file (file_name, file_date)
                        VALUES (%s, %s)
                        RETURNING id;
                        """,
                        (fname, file_date),
                    )
                    file_id = cur.fetchone()[0]

                    row_count = 0
                    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            cur.execute(
                                """
                                INSERT INTO staging.raw_row (file_id, row_data)
                                VALUES (%s, %s)
                                """,
                                (file_id, json.dumps(row)),
                            )
                            row_count += 1

                    cur.execute(
                        "UPDATE staging.raw_file SET row_count = %s WHERE id = %s;",
                        (row_count, file_id),
                    )

                    cur.execute("COMMIT;")
                    logger.info(f"  -> {row_count} rows imported.")

                except Exception as e:
                    cur.execute("ROLLBACK;")
                    logger.error(f"FAILED: {fname}  Reason: {e}")

    logger.info("Import complete")


if __name__ == "__main__":
    main()
