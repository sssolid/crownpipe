"""
Database-backed audit tracking system for media pipeline.

Replaces JSON file-based audit logs with PostgreSQL storage.
Tracks who uploaded files, when, and what actions were performed.
"""
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from crownpipe.common.db import get_conn
from crownpipe.common.exceptions import DatabaseError
from crownpipe.common.logger import get_pipeline_logger

logger = get_pipeline_logger(__name__, 'media')


@dataclass
class AuditEntry:
    """Single audit log entry."""
    id: Optional[int]
    timestamp: datetime
    user_id: str
    action: str
    details: Optional[str] = None
    source_file: Optional[str] = None
    execution_time_ms: Optional[int] = None


@dataclass
class FormatEntry:
    """Format generation entry."""
    id: Optional[int]
    format_name: str
    generated_at: datetime
    file_path: Optional[str] = None
    file_size_bytes: Optional[int] = None


@dataclass
class ProductionSyncEntry:
    """Production sync entry."""
    id: Optional[int]
    synced_at: datetime
    files_synced: int
    total_bytes: int


@dataclass
class ProductAudit:
    """Complete audit trail for a product."""
    product_number: str
    upload_history: List[AuditEntry]
    formats_generated: List[FormatEntry]
    production_syncs: List[ProductionSyncEntry]


class AuditLog:
    """Manages audit logs for products in database."""
    
    @staticmethod
    def _ensure_schema():
        """Ensure audit schema and tables exist."""
        with get_conn() as conn:
            with conn.cursor() as cur:
                # Create audit schema
                cur.execute("CREATE SCHEMA IF NOT EXISTS audit;")
                
                # Product audit table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS audit.product_audit (
                        id BIGSERIAL PRIMARY KEY,
                        product_number VARCHAR(100) NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        user_id VARCHAR(100),
                        action VARCHAR(100) NOT NULL,
                        details TEXT,
                        source_file VARCHAR(255),
                        execution_time_ms INTEGER,
                        context JSONB
                    );
                """)
                
                # Format history table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS audit.format_history (
                        id BIGSERIAL PRIMARY KEY,
                        product_number VARCHAR(100) NOT NULL,
                        format_name VARCHAR(100) NOT NULL,
                        generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        file_path TEXT,
                        file_size_bytes BIGINT
                    );
                """)
                
                # Production sync table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS audit.production_sync (
                        id BIGSERIAL PRIMARY KEY,
                        product_number VARCHAR(100) NOT NULL,
                        synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        files_synced INTEGER NOT NULL,
                        total_bytes BIGINT NOT NULL
                    );
                """)
                
                # Indexes
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_product_audit_number 
                    ON audit.product_audit(product_number, timestamp DESC);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_product_audit_action 
                    ON audit.product_audit(action);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_format_history_number 
                    ON audit.format_history(product_number);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_production_sync_number 
                    ON audit.production_sync(product_number, synced_at DESC);
                """)
                
                conn.commit()
    
    @staticmethod
    def get_samba_username(file_path: Path) -> str:
        """
        Attempt to get the Samba username who owns/created a file.
        Falls back to filesystem owner if Samba info unavailable.
        
        Args:
            file_path: Path to file
            
        Returns:
            Username string
        """
        try:
            # Try to get file owner from filesystem
            stat_info = file_path.stat()
            uid = stat_info.st_uid
            
            # Try to resolve to username
            import pwd
            try:
                user_info = pwd.getpwuid(uid)
                username = user_info.pw_name
            except KeyError:
                username = f"uid:{uid}"
            
            # For Samba shares, check if we can get more info from extended attributes
            try:
                result = subprocess.run(
                    ["getfattr", "-n", "user.DOSATTRIB", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                # If successful, we know it came through Samba
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            return username
            
        except Exception as e:
            logger.warning(f"Could not determine username for {file_path}", error=str(e))
            return "unknown"
    
    @staticmethod
    def load(product_number: str) -> Optional[ProductAudit]:
        """
        Load audit log for a product from database.
        
        Args:
            product_number: Product number
            
        Returns:
            ProductAudit or None if doesn't exist
        """
        try:
            AuditLog._ensure_schema()
            
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Load upload history
                    cur.execute("""
                        SELECT id, timestamp, user_id, action, details, source_file, execution_time_ms
                        FROM audit.product_audit
                        WHERE product_number = %s
                        ORDER BY timestamp DESC
                    """, (product_number,))
                    
                    upload_history = [
                        AuditEntry(
                            id=row[0],
                            timestamp=row[1],
                            user_id=row[2],
                            action=row[3],
                            details=row[4],
                            source_file=row[5],
                            execution_time_ms=row[6]
                        )
                        for row in cur.fetchall()
                    ]
                    
                    # Load format history
                    cur.execute("""
                        SELECT id, format_name, generated_at, file_path, file_size_bytes
                        FROM audit.format_history
                        WHERE product_number = %s
                        ORDER BY generated_at DESC
                    """, (product_number,))
                    
                    formats_generated = [
                        FormatEntry(
                            id=row[0],
                            format_name=row[1],
                            generated_at=row[2],
                            file_path=row[3],
                            file_size_bytes=row[4]
                        )
                        for row in cur.fetchall()
                    ]
                    
                    # Load production sync history
                    cur.execute("""
                        SELECT id, synced_at, files_synced, total_bytes
                        FROM audit.production_sync
                        WHERE product_number = %s
                        ORDER BY synced_at DESC
                    """, (product_number,))
                    
                    production_syncs = [
                        ProductionSyncEntry(
                            id=row[0],
                            synced_at=row[1],
                            files_synced=row[2],
                            total_bytes=row[3]
                        )
                        for row in cur.fetchall()
                    ]
                    
                    if not upload_history:
                        return None
                    
                    return ProductAudit(
                        product_number=product_number,
                        upload_history=upload_history,
                        formats_generated=formats_generated,
                        production_syncs=production_syncs
                    )
        except Exception as e:
            logger.error(f"Failed to load audit log for {product_number}", exc_info=e)
            return None
    
    @staticmethod
    def create_or_update(
        product_number: str,
        action: str,
        user_id: Optional[str] = None,
        source_file: Optional[Path] = None,
        details: Optional[str] = None,
        execution_time_ms: Optional[int] = None
    ):
        """
        Create or update audit log with a new entry.
        
        Args:
            product_number: Product number
            action: Action performed
            user_id: Username (auto-detected from source_file if not provided)
            source_file: Source file (used for username detection)
            details: Additional details
            execution_time_ms: Execution time in milliseconds
        """
        try:
            AuditLog._ensure_schema()
            
            # Determine user if not provided
            if user_id is None and source_file is not None:
                user_id = AuditLog.get_samba_username(source_file)
            elif user_id is None:
                user_id = "system"
            
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO audit.product_audit 
                        (product_number, user_id, action, details, source_file, execution_time_ms)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        product_number,
                        user_id,
                        action,
                        details,
                        str(source_file.name) if source_file else None,
                        execution_time_ms
                    ))
                    conn.commit()
            
            logger.info(
                f"Audit: {action}",
                product_number=product_number,
                user_id=user_id,
                execution_time_ms=execution_time_ms
            )
        except Exception as e:
            logger.error(
                f"Failed to create audit entry for {product_number}",
                exc_info=e,
                product_number=product_number,
                action=action
            )
    
    @staticmethod
    def add_format(
        product_number: str,
        format_name: str,
        file_path: Optional[Path] = None
    ):
        """
        Record that a format was generated.
        
        Args:
            product_number: Product number
            format_name: Name of format generated
            file_path: Path to generated file
        """
        try:
            AuditLog._ensure_schema()
            
            file_size_bytes = None
            if file_path and file_path.exists():
                file_size_bytes = file_path.stat().st_size
            
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO audit.format_history 
                        (product_number, format_name, file_path, file_size_bytes)
                        VALUES (%s, %s, %s, %s)
                    """, (
                        product_number,
                        format_name,
                        str(file_path) if file_path else None,
                        file_size_bytes
                    ))
                    conn.commit()
            
            logger.debug(
                f"Format added: {format_name}",
                product_number=product_number,
                format_name=format_name
            )
        except Exception as e:
            logger.error(
                f"Failed to add format entry for {product_number}",
                exc_info=e,
                product_number=product_number,
                format_name=format_name
            )
    
    @staticmethod
    def update_production_sync(product_number: str, files_synced: int, total_bytes: int):
        """
        Record that product was synced to production.
        
        Args:
            product_number: Product number
            files_synced: Number of files synced
            total_bytes: Total bytes synced
        """
        try:
            AuditLog._ensure_schema()
            
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO audit.production_sync 
                        (product_number, files_synced, total_bytes)
                        VALUES (%s, %s, %s)
                    """, (product_number, files_synced, total_bytes))
                    conn.commit()
            
            logger.info(
                f"Production sync recorded",
                product_number=product_number,
                files_synced=files_synced,
                total_bytes=total_bytes
            )
        except Exception as e:
            logger.error(
                f"Failed to record production sync for {product_number}",
                exc_info=e,
                product_number=product_number
            )


def migrate_json_audits_to_database():
    """
    Migrate old JSON-based audit logs to database.
    
    This function scans the products directory for .audit.json files
    and imports them into the database.
    """
    from crownpipe.common.paths import MEDIA_PRODUCTS
    import json
    
    if not MEDIA_PRODUCTS.exists():
        logger.warning("Products directory does not exist")
        return
    
    migrated_count = 0
    error_count = 0
    
    for product_dir in MEDIA_PRODUCTS.iterdir():
        if not product_dir.is_dir():
            continue
        
        audit_file = product_dir / ".audit.json"
        if not audit_file.exists():
            continue
        
        try:
            with open(audit_file) as f:
                data = json.load(f)
            
            product_number = data.get('product_number')
            if not product_number:
                continue
            
            # Migrate upload history
            for entry in data.get('upload_history', []):
                AuditLog.create_or_update(
                    product_number=product_number,
                    action=entry.get('action', 'unknown'),
                    user_id=entry.get('user', 'unknown'),
                    details=entry.get('details'),
                    source_file=Path(entry['source_file']) if entry.get('source_file') else None
                )
            
            # Migrate formats
            for format_name in data.get('formats_generated', []):
                AuditLog.add_format(product_number, format_name)
            
            # Migrate production sync (if available)
            if data.get('last_production_sync'):
                AuditLog.update_production_sync(product_number, 0, 0)
            
            # Rename old audit file
            audit_file.rename(product_dir / ".audit.json.migrated")
            
            migrated_count += 1
            logger.info(f"Migrated audit for {product_number}")
            
        except Exception as e:
            error_count += 1
            logger.error(f"Failed to migrate audit for {product_dir.name}", exc_info=e)
    
    logger.info(
        f"Migration complete: {migrated_count} successful, {error_count} errors"
    )
