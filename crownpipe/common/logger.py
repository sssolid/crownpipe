"""Shared logging configuration."""
import logging
import sys
from typing import Optional


def get_logger(
    name: str,
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    Get a configured logger instance.
    
    Creates a logger with consistent formatting and console output.
    Avoids duplicate handlers if called multiple times for the same name.
    
    Args:
        name: Logger name (usually __name__)
        level: Logging level (default INFO)
        format_string: Custom format string (optional)
    
    Returns:
        Configured logger instance
        
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing started")
        2024-11-29 10:30:00 [module.name] INFO: Processing started
    """
    if format_string is None:
        format_string = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(format_string, datefmt="%Y-%m-%d %H:%M:%S")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger
