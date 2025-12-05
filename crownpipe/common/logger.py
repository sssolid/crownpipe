"""
Centralized logging system for CrownPipe.

Features:
- Structured logging with context
- Multiple handlers: console, rotating file, database
- Performance metrics (execution time)
- Integration with Django logging
"""
import logging
import logging.handlers
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from crownpipe.common.exceptions import DatabaseError


class ContextFilter(logging.Filter):
    """Add context fields to log records."""
    
    def __init__(self, context: dict | None = None):
        super().__init__()
        self.context = context or {}
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Add context fields to record
        for key, value in self.context.items():
            setattr(record, key, value)
        
        # Ensure all expected fields exist
        for field in ['pipeline', 'product_number', 'user_id', 'execution_time_ms']:
            if not hasattr(record, field):
                setattr(record, field, None)
        
        return True


class DatabaseHandler(logging.Handler):
    """Log handler that writes to PostgreSQL database."""
    
    def __init__(self, get_connection_func):
        super().__init__()
        self.get_connection = get_connection_func
        self._ensure_schema()
    
    def _ensure_schema(self):
        """Ensure logs schema and table exist."""
        try:
            from crownpipe.common.db import get_conn
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Create logs schema
                    cur.execute("CREATE SCHEMA IF NOT EXISTS logs;")
                    
                    # Create pipeline_logs table
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS logs.pipeline_logs (
                            id BIGSERIAL PRIMARY KEY,
                            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            level VARCHAR(20) NOT NULL,
                            pipeline VARCHAR(50),
                            module VARCHAR(100) NOT NULL,
                            message TEXT NOT NULL,
                            context JSONB,
                            exception TEXT,
                            user_id VARCHAR(100),
                            execution_time_ms INTEGER
                        );
                    """)
                    
                    # Create indexes
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_logs_timestamp 
                        ON logs.pipeline_logs(timestamp DESC);
                    """)
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_logs_level 
                        ON logs.pipeline_logs(level);
                    """)
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_logs_pipeline 
                        ON logs.pipeline_logs(pipeline);
                    """)
                    
                    conn.commit()
        except Exception as e:
            # Don't fail if we can't create schema (might not have permissions yet)
            print(f"Warning: Could not ensure log schema: {e}", file=sys.stderr)
    
    def emit(self, record: logging.LogRecord):
        """Write log record to database."""
        try:
            # Build context from record attributes
            context = {}
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                               'levelname', 'levelno', 'lineno', 'module', 'msecs',
                               'message', 'pathname', 'process', 'processName',
                               'relativeCreated', 'thread', 'threadName', 'exc_info',
                               'exc_text', 'stack_info', 'timestamp', 'level', 'pipeline',
                               'user_id', 'execution_time_ms']:
                    context[key] = value
            
            # Get exception text if present
            exc_text = None
            if record.exc_info:
                exc_text = self.format(record)
            
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO logs.pipeline_logs 
                        (timestamp, level, pipeline, module, message, context, 
                         exception, user_id, execution_time_ms)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                    """, (
                        datetime.fromtimestamp(record.created),
                        record.levelname,
                        getattr(record, 'pipeline', None),
                        record.name,
                        record.getMessage(),
                        str(context) if context else None,
                        exc_text,
                        getattr(record, 'user_id', None),
                        getattr(record, 'execution_time_ms', None)
                    ))
                    conn.commit()
        except Exception:
            self.handleError(record)


class PipelineLogger:
    """
    Enhanced logger for pipeline operations.
    
    Provides structured logging with context and performance tracking.
    """
    
    def __init__(self, name: str, pipeline: str | None = None):
        self.logger = logging.getLogger(name)
        self.pipeline = pipeline or name.split('.')[0] if '.' in name else name
        self.context: dict[str, Any] = {'pipeline': self.pipeline}
    
    def _log(self, level: int, message: str, **kwargs):
        """Internal logging method that adds context."""
        extra = {**self.context, **kwargs}
        self.logger.log(level, message, extra=extra)
    
    def debug(self, message: str, **kwargs):
        """Log debug message with context."""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message with context."""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with context."""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, exc_info: Exception | None = None, **kwargs):
        """Log error message with context and optional exception."""
        if exc_info:
            self.logger.error(message, exc_info=exc_info, extra={**self.context, **kwargs})
        else:
            self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, exc_info: Exception | None = None, **kwargs):
        """Log critical message with context and optional exception."""
        if exc_info:
            self.logger.critical(message, exc_info=exc_info, extra={**self.context, **kwargs})
        else:
            self._log(logging.CRITICAL, message, **kwargs)
    
    def set_context(self, **kwargs):
        """Set persistent context for all subsequent log messages."""
        self.context.update(kwargs)
    
    def clear_context(self):
        """Clear all context except pipeline."""
        self.context = {'pipeline': self.pipeline}
    
    @contextmanager
    def log_execution(self, operation: str, **context):
        """
        Context manager that logs execution time and handles errors.
        
        Usage:
            with logger.log_execution('process_file', product_number='12345'):
                # do work
                pass
        """
        start_time = time.time()
        self.info(f"Starting {operation}", **context)
        
        try:
            yield
            execution_time_ms = int((time.time() - start_time) * 1000)
            self.info(
                f"Completed {operation}",
                execution_time_ms=execution_time_ms,
                **context
            )
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            self.error(
                f"Failed {operation}: {e}",
                exc_info=e,
                execution_time_ms=execution_time_ms,
                **context
            )
            raise


def setup_logging(
    log_dir: Path | None = None,
    log_to_db: bool = True,
    log_level: int = logging.INFO
) -> None:
    """
    Configure logging for the entire application.
    
    Args:
        log_dir: Directory for log files (None = /var/log/crownpipe)
        log_to_db: Whether to log to database
        log_level: Minimum log level to capture
    """
    if log_dir is None:
        log_dir = Path("/var/log/crownpipe")
    
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Console handler with color-coded output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "crownpipe.log",
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=10
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(pipeline)s.%(name)s: %(message)s '
        '[user=%(user_id)s, product=%(product_number)s, exec_time=%(execution_time_ms)sms]',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Database handler (if enabled)
    if log_to_db:
        try:
            from crownpipe.common.db import get_conn
            db_handler = DatabaseHandler(get_conn)
            db_handler.setLevel(logging.INFO)  # Only INFO and above to DB
            root_logger.addHandler(db_handler)
        except Exception as e:
            print(f"Warning: Could not enable database logging: {e}", file=sys.stderr)


def get_pipeline_logger(name: str, pipeline: str | None = None) -> PipelineLogger:
    """
    Get a pipeline logger instance.
    
    Args:
        name: Logger name (usually __name__)
        pipeline: Pipeline name (auto-detected if None)
    
    Returns:
        PipelineLogger instance
    
    Example:
        >>> logger = get_pipeline_logger(__name__)
        >>> logger.info("Processing started", product_number="12345")
    """
    return PipelineLogger(name, pipeline)


# Maintain backward compatibility with old get_logger function
def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Get a basic logger (backward compatibility).
    
    For new code, use get_pipeline_logger() instead.
    """
    return logging.getLogger(name)
