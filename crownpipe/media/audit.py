#!/usr/bin/env python3
"""
Audit tracking system for media pipeline.
Tracks who uploaded files, when, and what actions were performed.
"""
import json
import os
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from crownpipe.common.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AuditEntry:
    """Single audit log entry."""
    timestamp: str
    user: str
    action: str
    details: Optional[str] = None
    source_file: Optional[str] = None


@dataclass
class ProductAudit:
    """Complete audit trail for a product."""
    product_number: str
    upload_history: List[AuditEntry]
    formats_generated: List[str]
    last_production_sync: Optional[str] = None


class AuditLog:
    """Manages audit logs for products."""
    
    AUDIT_FILENAME = ".audit.json"
    
    @staticmethod
    def get_audit_path(product_dir: Path) -> Path:
        """Get path to audit file for a product."""
        return product_dir / AuditLog.AUDIT_FILENAME
    
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
                # Check for Samba-specific extended attributes
                result = subprocess.run(
                    ["getfattr", "-n", "user.DOSATTRIB", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                # If successful, we know it came through Samba
                # The username from filesystem should be correct
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            
            return username
            
        except Exception as e:
            logger.warning(f"Could not determine username for {file_path}: {e}")
            return "unknown"
    
    @staticmethod
    def load(product_dir: Path) -> Optional[ProductAudit]:
        """
        Load audit log for a product.
        
        Args:
            product_dir: Product directory
            
        Returns:
            ProductAudit or None if doesn't exist
        """
        audit_path = AuditLog.get_audit_path(product_dir)
        
        if not audit_path.exists():
            return None
        
        try:
            with open(audit_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Convert dict entries back to AuditEntry objects
            upload_history = [
                AuditEntry(**entry) for entry in data.get("upload_history", [])
            ]
            
            return ProductAudit(
                product_number=data["product_number"],
                upload_history=upload_history,
                formats_generated=data.get("formats_generated", []),
                last_production_sync=data.get("last_production_sync")
            )
        except Exception as e:
            logger.error(f"Failed to load audit log from {audit_path}: {e}")
            return None
    
    @staticmethod
    def save(product_dir: Path, audit: ProductAudit):
        """
        Save audit log for a product.
        
        Args:
            product_dir: Product directory
            audit: Audit data to save
        """
        audit_path = AuditLog.get_audit_path(product_dir)
        product_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Convert to dict for JSON serialization
            data = {
                "product_number": audit.product_number,
                "upload_history": [asdict(entry) for entry in audit.upload_history],
                "formats_generated": audit.formats_generated,
                "last_production_sync": audit.last_production_sync
            }
            
            with open(audit_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"Failed to save audit log to {audit_path}: {e}")
    
    @staticmethod
    def create_or_update(
        product_dir: Path,
        product_number: str,
        action: str,
        user: Optional[str] = None,
        source_file: Optional[Path] = None,
        details: Optional[str] = None
    ):
        """
        Create or update audit log with a new entry.
        
        Args:
            product_dir: Product directory
            product_number: Product number
            action: Action performed
            user: Username (auto-detected from source_file if not provided)
            source_file: Source file (used for username detection)
            details: Additional details
        """
        # Load existing audit or create new
        audit = AuditLog.load(product_dir)
        if audit is None:
            audit = ProductAudit(
                product_number=product_number,
                upload_history=[],
                formats_generated=[]
            )
        
        # Determine user if not provided
        if user is None and source_file is not None:
            user = AuditLog.get_samba_username(source_file)
        elif user is None:
            user = "system"
        
        # Create new entry
        entry = AuditEntry(
            timestamp=datetime.utcnow().isoformat() + "Z",
            user=user,
            action=action,
            details=details,
            source_file=str(source_file.name) if source_file else None
        )
        
        audit.upload_history.append(entry)
        
        # Save
        AuditLog.save(product_dir, audit)
        logger.info(f"Audit: {product_number} - {action} by {user}")
    
    @staticmethod
    def add_format(product_dir: Path, format_name: str):
        """
        Record that a format was generated.
        
        Args:
            product_dir: Product directory
            format_name: Name of format generated
        """
        audit = AuditLog.load(product_dir)
        if audit is None:
            logger.warning(f"No audit log found for {product_dir}")
            return
        
        if format_name not in audit.formats_generated:
            audit.formats_generated.append(format_name)
            AuditLog.save(product_dir, audit)
    
    @staticmethod
    def update_production_sync(product_dir: Path):
        """
        Record that product was synced to production.
        
        Args:
            product_dir: Product directory
        """
        audit = AuditLog.load(product_dir)
        if audit is None:
            logger.warning(f"No audit log found for {product_dir}")
            return
        
        audit.last_production_sync = datetime.utcnow().isoformat() + "Z"
        AuditLog.save(product_dir, audit)


def main():
    """Test audit system."""
    from crownpipe.common.paths import get_product_dir
    
    test_dir = Path("/tmp/test_product")
    test_dir.mkdir(exist_ok=True)
    
    # Create initial audit
    AuditLog.create_or_update(
        test_dir,
        "TEST123",
        "initial_upload",
        user="jsmith",
        details="Testing audit system"
    )
    
    # Add another action
    AuditLog.create_or_update(
        test_dir,
        "TEST123",
        "bg_removal_success"
    )
    
    # Add format
    AuditLog.add_format(test_dir, "web/1000x1000_72dpi_jpeg")
    
    # Load and print
    audit = AuditLog.load(test_dir)
    if audit:
        print(json.dumps(asdict(audit), indent=2, default=str))


if __name__ == "__main__":
    main()
