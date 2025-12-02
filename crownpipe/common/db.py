"""Database connection utilities."""
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import psycopg2
from psycopg2.extensions import connection


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
                if h == host and p == port and d == database and u == user:
                    return pwd
    
    raise ValueError(f"No matching entry in .pgpass for {user}@{host}")


@contextmanager
def get_conn() -> Generator[connection, None, None]:
    """
    Get PostgreSQL connection using .pgpass credentials or environment variables.
    
    Connection parameters are read from:
    1. Environment variables (PG_PASSWORD, PG_HOST, etc.) - highest priority
    2. /var/lib/postgresql/.pgpass (system pgpass)
    3. ~/.pgpass (user pgpass)
    
    Environment variables:
        PG_HOST: Database host (default: 127.0.0.1)
        PG_PORT: Database port (default: 5432)
        PG_DATABASE: Database name (default: crown_marketing)
        PG_USER: Database user (default: crown_admin)
        PG_PASSWORD: Database password (overrides .pgpass)
    
    Yields:
        PostgreSQL connection object
        
    Raises:
        RuntimeError: If no password source found
        psycopg2.Error: On connection failure
        
    Example:
        >>> with get_conn() as conn:
        ...     with conn.cursor() as cur:
        ...         cur.execute("SELECT 1")
        ...         result = cur.fetchone()
    """
    host = os.getenv('PG_HOST', '127.0.0.1')
    port = os.getenv('PG_PORT', '5432')
    database = os.getenv('PG_DATABASE', 'crown_marketing')
    user = os.getenv('PG_USER', 'crown_admin')
    
    # Try environment variable first
    password = os.getenv('PG_PASSWORD')
    
    # Fall back to .pgpass
    if not password:
        # Try system pgpass
        pgpass_path = Path('/var/lib/postgresql/.pgpass')
        if pgpass_path.exists():
            try:
                password = get_pgpass_password(pgpass_path, host, port, database, user)
            except ValueError:
                pass
        
        # Try user's home directory
        if not password:
            home_pgpass = Path.home() / '.pgpass'
            if home_pgpass.exists():
                try:
                    password = get_pgpass_password(home_pgpass, host, port, database, user)
                except ValueError:
                    pass
        
        if not password:
            raise RuntimeError(
                "No password source found. Set PG_PASSWORD environment variable "
                "or create .pgpass file"
            )
    
    dsn = f"host={host} port={port} dbname={database} user={user} password={password}"
    
    conn = psycopg2.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()
