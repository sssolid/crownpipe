"""
Base pipeline class for unified pipeline structure.

All pipelines should inherit from BasePipeline and implement process_item().
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from crownpipe.common.config import get_settings
from crownpipe.common.exceptions import PipelineError
from crownpipe.common.logger import PipelineLogger, get_pipeline_logger


@dataclass
class PipelineStats:
    """Statistics for pipeline execution."""
    
    total_items: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    errors: Dict[str, int] = field(default_factory=dict)
    execution_time_ms: int = 0
    
    def record_success(self):
        """Record successful item processing."""
        self.total_items += 1
        self.successful += 1
    
    def record_failure(self, error: Optional[Exception] = None):
        """Record failed item processing."""
        self.total_items += 1
        self.failed += 1
        if error:
            error_type = type(error).__name__
            self.errors[error_type] = self.errors.get(error_type, 0) + 1
    
    def record_skip(self):
        """Record skipped item."""
        self.total_items += 1
        self.skipped += 1
    
    def __str__(self) -> str:
        """String representation of stats."""
        return (
            f"Processed: {self.total_items} | "
            f"Success: {self.successful} | "
            f"Failed: {self.failed} | "
            f"Skipped: {self.skipped} | "
            f"Time: {self.execution_time_ms}ms"
        )


class BasePipeline(ABC):
    """
    Base class for all pipelines.
    
    Provides common functionality:
    - Logging with context
    - Configuration management
    - Error handling
    - Statistics tracking
    """
    
    def __init__(self, pipeline_name: Optional[str] = None):
        """
        Initialize pipeline.
        
        Args:
            pipeline_name: Pipeline name for logging (auto-detected if None)
        """
        if pipeline_name is None:
            pipeline_name = self.__class__.__name__.lower().replace('pipeline', '')
        
        self.pipeline_name = pipeline_name
        self.settings = get_settings()
        self.logger = get_pipeline_logger(
            f"{self.__class__.__module__}.{self.__class__.__name__}",
            pipeline=pipeline_name
        )
        self.stats = PipelineStats()
    
    @abstractmethod
    def get_items(self) -> Iterable[Any]:
        """
        Get items to process.
        
        Returns:
            Iterable of items to process
        """
        pass
    
    @abstractmethod
    def process_item(self, item: Any) -> bool:
        """
        Process a single item.
        
        Args:
            item: Item to process
            
        Returns:
            True if successful, False if failed
            
        Raises:
            PipelineError: On processing error
        """
        pass
    
    def should_skip_item(self, item: Any) -> bool:
        """
        Check if item should be skipped.
        
        Override this method to implement skip logic.
        
        Args:
            item: Item to check
            
        Returns:
            True if item should be skipped
        """
        return False
    
    def run(self) -> PipelineStats:
        """
        Run the pipeline.
        
        Returns:
            Pipeline statistics
        """
        with self.logger.log_execution(f'{self.pipeline_name}_pipeline'):
            self.logger.info(f"Starting {self.pipeline_name} pipeline")
            
            try:
                items = list(self.get_items())
                self.logger.info(f"Found {len(items)} items to process")
                
                for item in items:
                    try:
                        # Check if should skip
                        if self.should_skip_item(item):
                            self.stats.record_skip()
                            self.logger.debug(f"Skipped {item}")
                            continue
                        
                        # Process item
                        self.logger.debug(f"Processing {item}")
                        success = self.process_item(item)
                        
                        if success:
                            self.stats.record_success()
                        else:
                            self.stats.record_failure()
                            
                    except PipelineError as e:
                        self.stats.record_failure(e)
                        self.logger.error(
                            f"Pipeline error processing {item}: {e.message}",
                            exc_info=e,
                            **e.context
                        )
                    except Exception as e:
                        self.stats.record_failure(e)
                        self.logger.error(
                            f"Unexpected error processing {item}",
                            exc_info=e
                        )
                
                self.logger.info(
                    f"Pipeline complete: {self.stats}",
                    total=self.stats.total_items,
                    successful=self.stats.successful,
                    failed=self.stats.failed
                )
                
            except Exception as e:
                self.logger.critical(
                    f"Pipeline failed catastrophically",
                    exc_info=e
                )
                raise
            
            return self.stats
    
    def validate_configuration(self):
        """
        Validate pipeline configuration.
        
        Override this method to add custom validation.
        Raises ConfigurationError if validation fails.
        """
        pass


class FileProcessingPipeline(BasePipeline):
    """
    Base class for pipelines that process files.
    
    Provides common file handling functionality.
    """
    
    def __init__(self, source_dir: Path, pipeline_name: Optional[str] = None):
        """
        Initialize file processing pipeline.
        
        Args:
            source_dir: Directory to scan for files
            pipeline_name: Pipeline name for logging
        """
        super().__init__(pipeline_name)
        self.source_dir = source_dir
        
        if not source_dir.exists():
            self.logger.warning(f"Source directory does not exist: {source_dir}")
    
    def get_items(self) -> Iterable[Path]:
        """
        Get files to process from source directory.
        
        Returns:
            Iterable of file paths
        """
        if not self.source_dir.exists():
            return []
        
        return [f for f in self.source_dir.iterdir() if f.is_file()]
    
    @abstractmethod
    def process_item(self, item: Path) -> bool:
        """
        Process a single file.
        
        Args:
            item: File path to process
            
        Returns:
            True if successful, False if failed
        """
        pass
