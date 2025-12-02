"""Configuration management."""
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
import os


class Config:
    """Configuration container with environment variable override support."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration.
        
        Loads configuration from YAML file if provided.
        Environment variables with CROWNPIPE_ prefix override config file values.
        
        Args:
            config_path: Path to YAML config file (optional)
            
        Example:
            >>> config = Config(Path("/etc/crownpipe/config.yaml"))
            >>> db_host = config.get("db_host", "localhost")
        """
        self._config: Dict[str, Any] = {}
        
        if config_path and config_path.exists():
            with open(config_path) as f:
                self._config = yaml.safe_load(f) or {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get config value, checking environment first.
        
        Environment variables take precedence over config file.
        Env var name is constructed as CROWNPIPE_{KEY_UPPER}.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        # Check environment variable (uppercase with CROWNPIPE_ prefix)
        env_key = f"CROWNPIPE_{key.upper()}"
        env_value = os.getenv(env_key)
        if env_value is not None:
            return env_value
        
        # Check config file
        return self._config.get(key, default)
    
    def __getitem__(self, key: str) -> Any:
        """
        Dictionary-style access (raises KeyError if not found).
        
        Args:
            key: Configuration key
            
        Returns:
            Configuration value
            
        Raises:
            KeyError: If key not found and no default
        """
        value = self.get(key)
        if value is None:
            raise KeyError(f"Config key '{key}' not found")
        return value
    
    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value at runtime.
        
        Args:
            key: Configuration key
            value: Configuration value
        """
        self._config[key] = value
    
    def __contains__(self, key: str) -> bool:
        """
        Check if key exists in configuration.
        
        Args:
            key: Configuration key
            
        Returns:
            True if key exists
        """
        env_key = f"CROWNPIPE_{key.upper()}"
        return os.getenv(env_key) is not None or key in self._config
