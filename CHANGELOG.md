# Changelog

All notable changes to CrownPipe will be documented in this file.

## [3.0.0] - 2024-12-03

### Major Refactoring Release

#### Added
- **Django Dashboard**: Complete replacement of Flask with Django framework
  - HTMX integration for interactive UI without JavaScript
  - Real-time auto-refreshing statistics
  - Media pipeline monitoring views
  - Data pipeline monitoring views
  - Log viewing and searching interface
  - REST API framework (foundation)
  
- **Centralized Logging System**
  - Three-tier logging: console, rotating file, PostgreSQL database
  - Structured logging with context (product_number, user_id, etc.)
  - Execution time tracking
  - Log querying via database or Django admin
  - `logs.pipeline_logs` table with indexes for performance
  
- **Database Audit System**
  - Migrated from JSON files to PostgreSQL
  - `audit.product_audit` - Complete audit trail for each product
  - `audit.format_history` - Format generation tracking
  - `audit.production_sync` - Production deployment history
  - Migration tool for existing JSON audit files
  
- **Unified Pipeline Architecture**
  - `BasePipeline` base class for all pipelines
  - `FileProcessingPipeline` for file-based pipelines
  - Consistent error handling across all pipelines
  - Statistics tracking (success/fail/skip counts)
  - Proper logging context throughout
  
- **Enhanced Configuration Management**
  - Pydantic-based validation with type checking
  - Environment variable support with `CROWNPIPE_` prefix
  - Settings classes for each component
  - Integration with Django settings
  - Hot-reload capability (for development)
  
- **Custom Exception Hierarchy**
  - `CrownPipeError` base exception
  - Pipeline-specific exceptions
  - Context preservation in exceptions
  - Better error messages and debugging
  
- **Management Scripts**
  - `bin/migrate-audit-logs` - Migrate JSON to database
  - `setup.sh` - Automated installation script
  - All pipelines updated as proper entry points

#### Changed
- **All Pipeline Modules Refactored**
  - `rename_incoming.py` - Now inherits from FileProcessingPipeline
  - `bgremove.py` - Enhanced error handling and logging
  - `prepare_formatting.py` - Consistent with new architecture
  - `format_pipeline.py` - Better EXIF handling
  - `deploy_production.py` - Improved sync logic
  - `filemaker_importer.py` - New validation and error handling
  
- **Configuration System**
  - Moved from simple dict-based to Pydantic models
  - Better validation and error messages
  - Environment variable support throughout
  
- **File Structure**
  - Reorganized for better separation of concerns
  - Common utilities properly centralized
  - Django apps in separate directory
  
- **Logging**
  - All `print()` statements replaced with proper logging
  - Context added to every log message
  - Performance metrics tracked automatically
  
#### Removed
- **Flask Dashboard** - Completely removed in favor of Django
- **JSON Audit Files** - Migrated to database
- **Hardcoded Paths** - Now configurable via settings
- **Scattered Configuration** - Unified into single system

#### Fixed
- Database connection handling with proper error messages
- File permission detection for Samba uploads
- Memory leaks in long-running processes
- Race conditions in file processing
- Improper error handling in background removal
- Missing type hints throughout codebase

#### Migration Notes
- Backup all data before upgrading
- Run `bin/migrate-audit-logs` to migrate audit data
- Update systemd service files
- Create new `.env` file with required settings
- Run Django migrations
- Update any custom scripts to use new imports

#### Breaking Changes
- Configuration file format changed (now uses Pydantic)
- Audit logs moved from JSON files to database
- Import paths changed (e.g., `from crownpipe.common.logger import get_pipeline_logger`)
- Flask dashboard removed (use Django dashboard)
- Some function signatures changed for consistency

## [2.1.0] - Previous Version

See git history for changes prior to v3.0.0 refactoring.
