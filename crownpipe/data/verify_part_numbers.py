#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Part Cleanup – Simplified Internal Resolver with Logging and Progress

Reads part numbers from numbers_to_verify.txt, resolves them via:
- Vendor mapping (POSRCGDP)
- Interchange (ININTER)
- Supersession (INSMFH)
- Leading-zero removal heuristics
- Decimal-merge and decimal zero-padding heuristics

Outputs a simple CSV with core resolution facts and logs detailed steps.
"""

import csv
import re
import os
import logging
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any

import dotenv

from tqdm import tqdm

from crownpipe.common.conn_filemaker import Filemaker
from crownpipe.common.conn_iseries import Iseries
from crownpipe.common.jvm import start_jvm

dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

# ==========================
# Configuration
# ==========================

# For inputs like "4798878.01", try merging ".01" and also zero-pad to ".010" etc.
DECIMAL_ALLOWED_PAD_LENGTHS = (2, 3)

# CSV output filename
CSV_OUTPUT_PATH = "part_cleanup_simple_summary.csv"


# ==========================
# Utilities
# ==========================

def normalize_part_number(part: str) -> str:
    """Remove non-alphanumeric characters and uppercase."""
    if part is None:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(part)).upper()


# ==========================
# Caching Layer
# ==========================

class DataCaches:
    """
    Caches data from AS/400 and FileMaker to avoid repeated queries.
    All keys are stored in normalized form (alnum-only, uppercase).
    """

    def __init__(self, iseries: Iseries, filemaker: Filemaker, logger: logging.Logger) -> None:
        self.iseries = iseries
        self.filemaker = filemaker
        self.logger = logger

        # AS/400 caches
        self._insmfh: Optional[Dict[str, Optional[str]]] = None  # SNSCHR -> SSUPER (or None)
        self._ininter: Optional[Dict[str, str]] = None          # ICPNO(child) -> IPTNO(parent)
        self._vendor_map: Optional[Dict[str, str]] = None       # SGVPT#(vendor) -> SGPTNO(internal)

        # FileMaker cache: normalized AS400_NumberStripped -> True/False/None
        self._fm_active_cache: Dict[str, Optional[bool]] = {}

    # ---------- AS/400: INSMFH ----------

    def load_insmfh(self) -> None:
        """Load INSMFH table into memory: SNSCHR -> SSUPER (both normalized)."""
        if self._insmfh is not None:
            return

        self.logger.info("Loading INSMFH (supersession) from AS/400...")
        self._insmfh = {}
        q = "SELECT SNSCHR, SSUPER FROM DSTDATA.INSMFH"
        self.iseries.cursor.execute(q)
        rows = self.iseries.cursor.fetchall()
        for snschr, ssuper in rows:
            key = normalize_part_number(snschr)
            if not key:
                continue
            master = normalize_part_number(ssuper) if ssuper else None
            self._insmfh[key] = master
        self.logger.info("Loaded INSMFH: %d rows", len(self._insmfh))

    @property
    def insmfh(self) -> Dict[str, Optional[str]]:
        if self._insmfh is None:
            self.load_insmfh()
        return self._insmfh  # type: ignore[return-value]

    # ---------- AS/400: ININTER ----------

    def load_ininter(self) -> None:
        """Load ININTER table into memory: ICPNO(child) -> IPTNO(parent) (normalized)."""
        if self._ininter is not None:
            return

        self.logger.info("Loading ININTER (interchange) from AS/400...")
        self._ininter = {}
        q = "SELECT ICPNO, IPTNO FROM DSTDATA.ININTER"
        self.iseries.cursor.execute(q)
        rows = self.iseries.cursor.fetchall()
        for icpno, iptno in rows:
            child = normalize_part_number(icpno)
            parent = normalize_part_number(iptno)
            if not child or not parent:
                continue
            self._ininter[child] = parent
        self.logger.info("Loaded ININTER: %d rows", len(self._ininter))

    @property
    def ininter(self) -> Dict[str, str]:
        if self._ininter is None:
            self.load_ininter()
        return self._ininter  # type: ignore[return-value]

    # ---------- AS/400: POSRCGDP (vendor numbers) ----------

    def load_vendor_map(self) -> None:
        """
        Load POSRCGDP table into memory: SGVPT#(vendor) -> SGPTNO(internal), both normalized.
        """
        if self._vendor_map is not None:
            return

        self.logger.info("Loading POSRCGDP (vendor numbers) from AS/400...")
        self._vendor_map = {}
        q = "SELECT SGVPT#, SGPTNO FROM DSTDATA.POSRCGDP"
        self.iseries.cursor.execute(q)
        rows = self.iseries.cursor.fetchall()
        for vendor, internal in rows:
            v = normalize_part_number(vendor)
            i = normalize_part_number(internal)
            if not v or not i:
                continue
            # Last one wins if duplicates; adjust if different behavior is needed.
            self._vendor_map[v] = i
        self.logger.info("Loaded POSRCGDP: %d rows", len(self._vendor_map))

    @property
    def vendor_map(self) -> Dict[str, str]:
        if self._vendor_map is None:
            self.load_vendor_map()
        return self._vendor_map  # type: ignore[return-value]

    def resolve_vendor_internal(self, supplied: str) -> Optional[str]:
        """
        If supplied number is a vendor/manufacturer number (SGVPT#),
        return associated internal SGPTNO, else None.
        """
        key = normalize_part_number(supplied)
        if not key:
            return None
        internal = self.vendor_map.get(key)
        if internal:
            self.logger.debug("Vendor mapping: supplied %s -> internal %s", supplied, internal)
        return internal

    # ---------- FileMaker: Master.ToggleActive ----------

    def fm_find_active_flag(self, snschr: str) -> Optional[bool]:
        """
        Check FileMaker for a given AS400_NumberStripped.
        Returns:
          - True  -> exists and Active (ToggleActive == 'Yes')
          - False -> exists and Inactive (ToggleActive != 'Yes')
          - None  -> not found
        Cached per normalized AS400_NumberStripped.
        """
        key = normalize_part_number(snschr)
        if not key:
            return None

        if key in self._fm_active_cache:
            return self._fm_active_cache[key]

        q = """
            SELECT ToggleActive
            FROM Master
            WHERE AS400_NumberStripped = ?
        """
        self.filemaker.cursor.execute(q, (key,))
        row = self.filemaker.cursor.fetchone()
        if not row:
            value: Optional[bool] = None
        else:
            value = (row[0] == "Yes")

        self._fm_active_cache[key] = value
        self.logger.debug("FileMaker lookup: %s -> %s", key, value)
        return value


# ==========================
# Decimal Recovery
# ==========================

def parse_decimal(original: str) -> Optional[Tuple[str, str]]:
    """
    If original contains a decimal and the suffix is numeric and non-empty,
    return (before, after). Else None.
    """
    if "." not in original:
        return None
    before, after = original.split(".", 1)
    if not after or not after.isdigit():
        return None
    return before, after


def generate_decimal_variants(original_input: str) -> List[str]:
    """
    Create merged variants ONLY if original contained a valid decimal portion.
    Try:
      - exact merge: before + after
      - zero-padded merges for allowed scales (e.g., .01 -> .010, .0 -> .00)
    Returns a list of raw variant strings (not normalized).
    """
    variants: List[str] = []
    parsed = parse_decimal(original_input)
    if not parsed:
        return variants

    before, after = parsed

    # Exact merge
    variants.append(before + after)

    # Zero-pad upward to allowed lengths
    for L in DECIMAL_ALLOWED_PAD_LENGTHS:
        if len(after) < L:
            variants.append(before + after.ljust(L, "0"))

    # Deduplicate while preserving order
    seen = set()
    uniq: List[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


# ==========================
# AS/400 Resolution
# ==========================

def resolve_supersession_chain(caches: DataCaches, start: str) -> str:
    """
    Follow SSUPER chain in INSMFH starting from `start` if present.
    If `start` is not in INSMFH, return `start` unchanged.
    """
    current = normalize_part_number(start)
    if not current:
        return current

    if current not in caches.insmfh:
        return current

    visited = set()
    while True:
        if current in visited:
            # Guard against circular data
            return current
        visited.add(current)

        ssuper = caches.insmfh.get(current)
        if not ssuper:
            return current
        current = ssuper


def resolve_master_number(caches: DataCaches, snschr: str) -> Optional[str]:
    """
    Unified AS/400 master resolver.

    Steps:
      1) Normalize supplied.
      2) If it is an interchange child (ICPNO), first map to parent (IPTNO).
      3) Follow supersession chain from that base, if any.
      4) The result is the master number.

    Returns:
      - Final master number string, or
      - None if nothing can be resolved at all.
    """
    key = normalize_part_number(snschr)
    if not key:
        return None

    # Step 1: interchange – if this key is an interchange child, map to parent
    base = caches.ininter.get(key, key)

    # Step 2: run supersession chain starting from base
    master = resolve_supersession_chain(caches, base)

    if not master:
        return None

    # We consider it known if either:
    #   - original key was an interchange child, OR
    #   - master exists as SNSCHR in INSMFH.
    if (key in caches.ininter) or (master in caches.insmfh):
        caches.logger.debug(
            "AS400 resolve: input %s -> base %s -> master %s",
            snschr, base, master
        )
        return master

    return None


# ==========================
# Evaluation Logic
# ==========================

def evaluate_part(caches: DataCaches, supplied: str) -> Dict[str, Any]:
    """
    Evaluate a single supplied part number.

    Resolution steps:
      1) Check vendor map.
      2) Determine initial candidate (vendor internal or normalized supplied).
      3) Try to resolve candidate directly in AS/400 (interchange + supersession).
      4) If not resolved, try leading-zero removal on the candidate.
      5) If still not resolved and NOT vendor, try decimal variants on the original supplied.
      6) If a master is found, check FileMaker for that master.
    """

    result: Dict[str, Any] = {
        "Supplied": supplied,
        "VendorFlag": False,
        "VendorInternal": None,
        "LeadingZeroRemoved": None,
        "DecimalVariantUsed": None,
        "AS400Found": False,
        "MasterNumber": None,
        "FMFound": False,
        "FMActive": None,
    }

    normalized_supplied = normalize_part_number(supplied)

    # 1) Vendor check
    vendor_internal = caches.resolve_vendor_internal(supplied)
    if vendor_internal:
        result["VendorFlag"] = True
        result["VendorInternal"] = vendor_internal
        candidate = vendor_internal
    else:
        candidate = normalized_supplied

    caches.logger.debug("Evaluating supplied: %s (candidate: %s, vendor: %s)",
                        supplied, candidate, result["VendorFlag"])

    master: Optional[str] = None

    # 2) Try direct AS/400 resolution for candidate
    if candidate:
        master = resolve_master_number(caches, candidate)

    # 3) If not resolved yet, try leading-zero removal on candidate
    if not master and candidate and candidate.startswith("0"):
        stripped = candidate.lstrip("0")
        if stripped:
            m2 = resolve_master_number(caches, stripped)
            if m2:
                master = m2
                result["LeadingZeroRemoved"] = stripped
                caches.logger.debug(
                    "Leading-zero heuristic: %s -> %s -> master %s",
                    candidate, stripped, master
                )

    # 4) Decimal variant fallback (only if not vendor and still no master)
    if not master and not result["VendorFlag"]:
        for variant in generate_decimal_variants(supplied):
            norm_variant = normalize_part_number(variant)
            if not norm_variant:
                continue
            m2 = resolve_master_number(caches, norm_variant)
            if m2:
                master = m2
                result["DecimalVariantUsed"] = norm_variant
                caches.logger.debug(
                    "Decimal heuristic: %s -> %s -> master %s",
                    supplied, norm_variant, master
                )
                break

    # 5) If a master was found, update AS400 and FM info
    if master:
        result["AS400Found"] = True
        result["MasterNumber"] = master

        fm_status = caches.fm_find_active_flag(master)
        if fm_status is None:
            result["FMFound"] = False
            result["FMActive"] = None
        else:
            result["FMFound"] = True
            result["FMActive"] = fm_status

    return result


# ==========================
# Reporting
# ==========================

def write_csv(results: List[Dict[str, Any]], csv_path: str) -> None:
    fieldnames = [
        "Supplied",
        "Vendor?",
        "VendorInternal",
        "LeadingZeroRemoved",
        "DecimalVariantUsed",
        "AS400 Found?",
        "Master Number",
        "FM Found?",
        "FM Active?",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = {
                "Supplied": r.get("Supplied"),
                "Vendor?": r.get("VendorFlag"),
                "VendorInternal": r.get("VendorInternal") or "",
                "LeadingZeroRemoved": r.get("LeadingZeroRemoved") or "",
                "DecimalVariantUsed": r.get("DecimalVariantUsed") or "",
                "AS400 Found?": r.get("AS400Found"),
                "Master Number": r.get("MasterNumber") or "",
                "FM Found?": r.get("FMFound"),
                "FM Active?": r.get("FMActive"),
            }
            writer.writerow(row)


# ==========================
# Logging Setup
# ==========================

def setup_logging() -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join("logs", f"part_cleanup_{timestamp}.log")

    logger = logging.getLogger("part_cleanup")
    logger.setLevel(logging.DEBUG)

    # Console handler (INFO and above)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter("[%(levelname)s] %(message)s")
    ch.setFormatter(ch_formatter)

    # File handler (DEBUG and above)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(fh_formatter)

    logger.addHandler(ch)
    logger.addHandler(fh)

    logger.info("Logging initialized. Log file: %s", log_path)
    return logger


# ==========================
# Main Execution
# ==========================

def main() -> None:
    logger = setup_logging()
    start_jvm()
    logger.info("JVM started.")

    # Read numbers from file, stripping whitespace and skipping blanks
    input_file = "numbers_to_verify.txt"
    if not os.path.exists(input_file):
        logger.error("Input file not found: %s", input_file)
        return

    part_numbers: List[str] = []
    with open(input_file, encoding="utf-8") as f:
        for line in f:
            part = line.strip()
            if part:
                part_numbers.append(part)

    total = len(part_numbers)
    if total == 0:
        logger.warning("No part numbers found in %s", input_file)
        return

    logger.info("Loaded %d part numbers from %s", total, input_file)

    results: List[Dict[str, Any]] = []

    # Update credentials/paths as appropriate
    with Iseries(server=os.getenv("ISERIES_SERVER"), user=os.getenv("ISERIES_USERNAME"), password=os.getenv("ISERIES_PASSWORD"),
                 database=os.getenv("ISERIES_DATABASE")) as iseries:

        with Filemaker(None) as filemaker:
            caches = DataCaches(iseries, filemaker, logger)

            # Preload AS/400 tables we know are reasonably sized
            caches.load_insmfh()
            caches.load_ininter()
            # Vendor map and FileMaker lookups are lazy-loaded as needed

            logger.info("Starting resolution of %d parts...", total)
            for input_part in tqdm(part_numbers, desc="Resolving parts", unit="part"):
                r = evaluate_part(caches, input_part)
                results.append(r)

    # Write CSV output only
    write_csv(results, CSV_OUTPUT_PATH)
    logger.info("CSV written to: %s", CSV_OUTPUT_PATH)

    # Summarize results
    vendor_count = sum(1 for r in results if r.get("VendorFlag"))
    leading_zero_count = sum(1 for r in results if r.get("LeadingZeroRemoved"))
    decimal_count = sum(1 for r in results if r.get("DecimalVariantUsed"))
    as400_found_count = sum(1 for r in results if r.get("AS400Found"))
    fm_found_count = sum(1 for r in results if r.get("FMFound"))
    fm_active_count = sum(1 for r in results if r.get("FMActive") is True)
    fm_inactive_count = sum(1 for r in results if r.get("FMActive") is False)

    logger.info("Resolution summary:")
    logger.info("  Total parts           : %d", total)
    logger.info("  Vendor numbers        : %d", vendor_count)
    logger.info("  Leading-zero guesses  : %d", leading_zero_count)
    logger.info("  Decimal guesses       : %d", decimal_count)
    logger.info("  AS/400 masters found  : %d", as400_found_count)
    logger.info("  FileMaker records     : %d", fm_found_count)
    logger.info("    Active              : %d", fm_active_count)
    logger.info("    Inactive            : %d", fm_inactive_count)
    logger.info("Done.")


if __name__ == "__main__":
    main()
