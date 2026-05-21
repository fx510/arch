#!/bin/bash
# Psiphon VPN Installer
# Downloads and configures Psiphon tunnel core

set -euo pipefail

echo "Starting Psiphon VPN installation..."

# Create directories
echo "Creating directories..."
mkdir -p /mnt/usr/local/bin
mkdir -p /mnt/etc/psiphon

# Download Psiphon binary
echo "Downloading Psiphon tunnel core..."
wget -O /mnt/usr/local/bin/psiphon \
    https://raw.githubusercontent.com/Psiphon-Labs/psiphon-tunnel-core-binaries/master/linux/psiphon-tunnel-core-x86_64 \
    --quiet --show-progress

# Make executable
echo "Setting permissions..."
chmod +x /mnt/usr/local/bin/psiphon

# Create psiphon user and group
echo "Creating psiphon user..."
arch-chroot /mnt groupadd -rf psiphon
arch-chroot /mnt useradd -r -g psiphon -s /usr/bin/nologin psiphon 2>/dev/null || echo "User already exists"

# Set ownership
chown root:psiphon /mnt/usr/local/bin/psiphon
chown -R psiphon:psiphon /mnt/etc/psiphon

echo "✓ Psiphon installation complete"
echo ""
echo "To enable Psiphon VPN after reboot:"
echo "  sudo systemctl enable psiphon.service"
echo "  sudo systemctl start psiphon.service"
echo ""
echo "Psiphon will run on:"
echo "  HTTP Proxy: localhost:8081"
echo "  SOCKS Proxy: localhost:1081"

