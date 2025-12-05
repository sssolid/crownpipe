#!/bin/bash
set -e

echo "==================================="
echo "CrownPipe v3.0 Setup Script"
echo "==================================="

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo "Please do not run as root. Run as crown-pipeline user."
   exit 1
fi

# Configuration
INSTALL_DIR="/opt/crownpipe"
VENV_DIR="$INSTALL_DIR/venv"
USER="crown-pipeline"
GROUP="marketing"

echo "Installing to: $INSTALL_DIR"

# Create directories
echo "Creating directories..."
sudo mkdir -p $INSTALL_DIR
sudo mkdir -p /var/log/crownpipe
sudo mkdir -p /srv/media/{inbox,processing,review,products,production,archive,errors}

# Set ownership
echo "Setting ownership..."
sudo chown -R $USER:$GROUP $INSTALL_DIR
sudo chown -R $USER:$GROUP /var/log/crownpipe
sudo chown -R $USER:$GROUP /srv/media

# Copy files
echo "Copying files..."
sudo cp -r * $INSTALL_DIR/
sudo chown -R $USER:$GROUP $INSTALL_DIR

# Create virtual environment
echo "Creating virtual environment..."
cd $INSTALL_DIR
python3.12 -m venv $VENV_DIR
source $VENV_DIR/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Database setup
echo "Setting up database..."
echo "NOTE: You'll need to run schema.sql manually as postgres user"
echo "sudo -u postgres psql crown_marketing < schema.sql"

# Django setup
echo "Setting up Django..."
cd $INSTALL_DIR/dashboard
python manage.py migrate
echo "Creating superuser (you'll be prompted for credentials)..."
python manage.py createsuperuser --noinput || true
python manage.py collectstatic --noinput

# Install systemd services
echo "Installing systemd services..."
sudo cp $INSTALL_DIR/systemd/*.service /etc/systemd/system/
sudo cp $INSTALL_DIR/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload

echo ""
echo "==================================="
echo "Setup Complete!"
echo "==================================="
echo ""
echo "Next steps:"
echo "1. Create .env file with your configuration"
echo "2. Set up database: sudo -u postgres psql crown_marketing < schema.sql"
echo "3. Enable services:"
echo "   sudo systemctl enable --now crownpipe-dashboard"
echo "   sudo systemctl enable --now crownpipe-rename-incoming.timer"
echo "   sudo systemctl enable --now crownpipe-bgremove.timer"
echo "   sudo systemctl enable --now crownpipe-format-pipeline.timer"
echo "   sudo systemctl enable --now crownpipe-deploy-production.timer"
echo "4. Access dashboard at: http://your_server:8000"
echo ""
