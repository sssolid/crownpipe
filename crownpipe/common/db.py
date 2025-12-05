"""
Database connection utilities with enhanced error handling.
"""
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import psycopg2
from psycopg2.extensions import connection

from crownpipe.common.exceptions import DatabaseError


def get_pgpass_password(
    pgpass_path: Path,
    host: str,
    port: str,
    database: str,
    user: str
) -> str:
    """
    Extract password from .pgpass file.
    
    Args:
        pgpass_path: Path to .pgpass file
        host: Database host
        port: Database port
        database: Database name
        user: Database user
        
    Returns:
        Password string
        
    Raises:
        FileNotFoundError: If .pgpass doesn't exist
        ValueError: If no matching entry found
    """
    if not pgpass_path.exists():
        raise FileNotFoundError(f"No .pgpass file at {pgpass_path}")
    
    with open(pgpass_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(':')
            if len(parts) == 5:
                h, p, d, u, pwd = parts
                # Support wildcards in .pgpass
                if ((h == '*' or h == host) and
                    (p == '*' or p == port) and
                    (d == '*' or d == database) and
                    (u == '*' or u == user)):
                    return pwd
    
    raise ValueError(f"No matching entry in .pgpass for {user}@{host}:{port}/{database}")


@contextmanager
def get_conn() -> Generator[connection, None, None]:
    """
    Get PostgreSQL connection using configuration.
    
    Connection parameters are read from:
    1. Environment variables (PG_PASSWORD, PG_HOST, etc.) - highest priority
    2. Settings configuration
    3. /var/lib/postgresql/.pgpass (system pgpass)
    4. ~/.pgpass (user pgpass)
    
    Environment variables:
        PG_HOST: Database host (default: 127.0.0.1)
        PG_PORT: Database port (default: 5432)
        PG_DATABASE: Database name (default: crown_marketing)
        PG_USER: Database user (default: crown_admin)
        PG_PASSWORD: Database password (overrides .pgpass)
    
    Yields:
        PostgreSQL connection object
        
    Raises:
        DatabaseError: If connection cannot be established
        
    Example:
        >>> with get_conn() as conn:
        ...     with conn.cursor() as cur:
        ...         cur.execute("SELECT 1")
        ...         result = cur.fetchone()
    """
    # Try to get settings, but fall back to env vars if not available
    try:
        from crownpipe.common.config import get_settings
        settings = get_settings()
        host = os.getenv('PG_HOST', settings.database.host)
        port = os.getenv('PG_PORT', str(settings.database.port))
        database = os.getenv('PG_DATABASE', settings.database.database)
        user = os.getenv('PG_USER', settings.database.user)
        password = os.getenv('PG_PASSWORD', settings.database.password)
    except Exception:
        # Fall back to environment variables only
        host = os.getenv('PG_HOST', '127.0.0.1')
        port = os.getenv('PG_PORT', '5432')
        database = os.getenv('PG_DATABASE', 'crown_marketing')
        user = os.getenv('PG_USER', 'crown_admin')
        password = os.getenv('PG_PASSWORD')
    
    # Try .pgpass if no password provided
    if not password:
        pgpass_paths = [
            Path('/var/lib/postgresql/.pgpass'),
            Path.home() / '.pgpass'
        ]
        
        for pgpass_path in pgpass_paths:
            if pgpass_path.exists():
                try:
                    password = get_pgpass_password(pgpass_path, host, port, database, user)
                    break
                except ValueError:
                    continue
        
        if not password:
            raise DatabaseError(
                "No password source found. Set PG_PASSWORD environment variable "
                "or create .pgpass file",
                context={'host': host, 'database': database, 'user': user}
            )
    
    dsn = f"host={host} port={port} dbname={database} user={user} password={password}"
    
    try:
        conn = psycopg2.connect(dsn)
    except psycopg2.Error as e:
        raise DatabaseError(
            f"Failed to connect to database: {e}",
            context={'host': host, 'database': database, 'user': user}
        ) from e
    
    try:
        yield conn
    except psycopg2.Error as e:
        conn.rollback()
        raise DatabaseError(
            f"Database error: {e}",
            context={'host': host, 'database': database}
        ) from e
    finally:
        conn.close()


def test_connection() -> bool:
    """
    Test database connection.
    
    Returns:
        True if connection successful, False otherwise
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True
    except DatabaseError:
        return False
