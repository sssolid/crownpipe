# CrownPipe v3.0 - Refactored

Crown Automotive media processing and data import pipeline - completely refactored with Django dashboard and centralized logging.

## What's New in v3.0

### Major Changes
- **Django Dashboard**: Replaced Flask with Django for extensible web interface
- **HTMX Integration**: Interactive UI without JavaScript complexity
- **Centralized Logging**: Logs to console, file, and database with structured context
- **Database Audit System**: Audit logs now stored in PostgreSQL instead of JSON files
- **Unified Pipeline Structure**: All pipelines inherit from base classes with consistent patterns
- **Enhanced Configuration**: Pydantic-based validation with environment variable support
- **Better Error Handling**: Custom exception hierarchy for clear error tracking

### Architecture

```
crownpipe/
├── common/              # Shared utilities
│   ├── config.py       # Configuration with validation
│   ├── db.py           # Database connections
│   ├── logger.py       # Centralized logging system
│   ├── exceptions.py   # Custom exception hierarchy
│   ├── paths.py        # Path constants
│   └── pipeline.py     # Base pipeline classes
│
├── media/              # Media processing pipeline
│   ├── rename_incoming.py
│   ├── bgremove.py
│   ├── prepare_formatting.py
│   ├── format_pipeline.py
│   ├── deploy_production.py
│   ├── audit.py        # Database audit system
│   └── fileutils.py
│
├── data/               # Data import pipeline
│   └── filemaker_importer.py
│
├── sync/               # Sync operations (future)
│
dashboard/              # Django web interface
├── manage.py
├── settings.py         # Django settings (integrates with CrownPipe config)
├── core/               # Main dashboard app
├── media_monitor/      # Media pipeline monitoring
├── data_monitor/       # Data pipeline monitoring
├── logs/               # Log viewing/searching
└── api/                # REST API (future)

bin/                    # Entry point scripts
```

## Installation

### 1. System Requirements

- Ubuntu Server 24.04
- PostgreSQL 16
- Python 3.12+
- ImageMagick (for media processing)
- rembg (for background removal)

### 2. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
    python3.12 python3.12-venv python3-pip \
    postgresql postgresql-contrib \
    imagemagick \
    getfattr  # For Samba username detection
```

### 3. Create Virtual Environment

```bash
cd /opt/crownpipe
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Database Setup

```bash
# Create database and user
sudo -u postgres psql << EOF
CREATE DATABASE crown_marketing OWNER postgres ENCODING 'UTF8';
CREATE ROLE crown_admin LOGIN PASSWORD 'your_password' CREATEDB;
GRANT CONNECT, TEMPORARY ON DATABASE crown_marketing TO crown_admin;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS logs;
\q
EOF

# Create .pgpass for passwordless access
cat > ~/.pgpass << EOF
localhost:5432:crown_marketing:crown_admin:your_password
EOF
chmod 600 ~/.pgpass
```

### 5. Configuration

Create `.env` file in project root:

```bash
# Database
PG_HOST=127.0.0.1
PG_PORT=5432
PG_DATABASE=crown_marketing
PG_USER=crown_admin
PG_PASSWORD=your_password

# Media Pipeline
CROWNPIPE_MEDIA_BASE=/srv/media

# Data Pipeline
CROWNPIPE_DATA_BASE=/srv/shares/marketing/filemaker
FILEMAKER_SERVER=your_server
FILEMAKER_PORT=443
FILEMAKER_DATABASE=your_db
FILEMAKER_USERNAME=your_user
FILEMAKER_PASSWORD=your_password

ISERIES_SERVER=your_server
ISERIES_DATABASE=your_db
ISERIES_USERNAME=your_user
ISERIES_PASSWORD=your_password

# Logging
CROWNPIPE_LOG_DIR=/var/log/crownpipe
CROWNPIPE_LOG_LEVEL=INFO
CROWNPIPE_LOG_TO_DATABASE=true

# Django Dashboard
DJANGO_SECRET_KEY=your_secret_key
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,your_server_ip
```

### 6. Initialize Database Schemas

```bash
# The logging and audit schemas will be created automatically on first run
# Or manually run:
python -c "from crownpipe.common.logger import setup_logging; setup_logging()"
python -c "from crownpipe.media.audit import AuditLog; AuditLog._ensure_schema()"
```

### 7. Migrate Old Audit Logs (if upgrading)

```bash
/opt/crownpipe/bin/migrate-audit-logs
```

### 8. Django Setup

```bash
cd /opt/crownpipe/dashboard
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

## Running the System

### Development

```bash
# Run Django development server
cd /opt/crownpipe/dashboard
python manage.py runserver 0.0.0.0:8000

# Run pipelines manually
/opt/crownpipe/bin/media-rename-incoming
/opt/crownpipe/bin/media-bgremove
/opt/crownpipe/bin/media-prepare-formatting
/opt/crownpipe/bin/media-format-pipeline
/opt/crownpipe/bin/media-deploy-production
/opt/crownpipe/bin/data-import-filemaker --apply
```

### Production (systemd)

Service files are in `systemd/` directory. Copy to `/etc/systemd/system/`:

```bash
sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload

# Enable and start services
sudo systemctl enable --now crownpipe-dashboard
sudo systemctl enable --now crownpipe-rename-incoming.timer
sudo systemctl enable --now crownpipe-bgremove.timer
sudo systemctl enable --now crownpipe-prepare-formatting.timer
sudo systemctl enable --now crownpipe-format-pipeline.timer
sudo systemctl enable --now crownpipe-deploy-production.timer

# Check status
sudo systemctl status crownpipe-dashboard
```

## Dashboard Access

Once running, access the dashboard at:
- **Development**: http://localhost:8000
- **Production**: http://your_server:8000

The dashboard provides:
- Real-time pipeline statistics (auto-refreshes every 5 seconds)
- Product status monitoring
- Log viewing and searching
- Manual pipeline triggers
- REST API access

## Logging

All logs are available in:
1. **Console**: Real-time output when running manually
2. **File**: `/var/log/crownpipe/crownpipe.log` (rotating, 50MB max, 10 backups)
3. **Database**: `logs.pipeline_logs` table for querying and analysis

View logs in dashboard at `/logs/` or query database directly:

```sql
SELECT * FROM logs.pipeline_logs 
WHERE pipeline = 'media' 
  AND level = 'ERROR' 
  AND timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;
```

## Audit System

Product audit trails are stored in PostgreSQL:

```sql
-- View all audit entries for a product
SELECT * FROM audit.product_audit 
WHERE product_number = '12345' 
ORDER BY timestamp DESC;

-- View format generation history
SELECT * FROM audit.format_history 
WHERE product_number = '12345';

-- View production sync history
SELECT * FROM audit.production_sync 
WHERE product_number = '12345';
```

## Configuration

### Environment Variables

All configuration can be set via environment variables with the `CROWNPIPE_` prefix:

```bash
CROWNPIPE_MEDIA_MAX_CONCURRENT_BGREMOVE=8
CROWNPIPE_MEDIA_BGREMOVE_TIMEOUT_SECONDS=600
CROWNPIPE_LOG_LEVEL=DEBUG
```

### Configuration File

Alternatively, create a YAML config file (not recommended for production):

```yaml
# config.yaml
media:
  max_concurrent_bgremove: 8
  bgremove_timeout_seconds: 600

logging:
  log_level: DEBUG
```

## Troubleshooting

### Pipelines Not Running

```bash
# Check service status
sudo systemctl status crownpipe-*.service

# View logs
sudo journalctl -u crownpipe-rename-incoming -f
```

### Database Connection Issues

```bash
# Test connection
python -c "from crownpipe.common.db import test_connection; print('OK' if test_connection() else 'FAILED')"
```

### Dashboard Not Loading

```bash
# Check Django logs
sudo journalctl -u crownpipe-dashboard -f

# Test manually
cd /opt/crownpipe/dashboard
python manage.py check
```

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-django

# Run tests
pytest
```

### Code Style

```bash
# Format code
black crownpipe/ dashboard/

# Check style
flake8 crownpipe/ dashboard/
```

## Migration from v2.x

1. **Backup existing data**:
   ```bash
   # Backup database
   pg_dump crown_marketing > backup.sql
   
   # Backup media files
   tar -czf media_backup.tar.gz /srv/media
   ```

2. **Install v3.0** following installation steps above

3. **Migrate audit logs**:
   ```bash
   /opt/crownpipe/bin/migrate-audit-logs
   ```

4. **Verify migration**:
   - Check dashboard shows correct statistics
   - Verify audit logs in database
   - Test pipeline execution

## License

Proprietary - Crown Automotive Sales Co., Inc.

## Support

For issues or questions, contact the development team.
