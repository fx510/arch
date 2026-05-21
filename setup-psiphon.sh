#!/bin/bash
# Post-installation script to set up Psiphon VPN
# Run this after the system is installed and booted

set -euo pipefail

echo "=========================================="
echo "  Psiphon VPN Setup"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root"
    echo "Usage: sudo ./setup-psiphon.sh"
    exit 1
fi

# Check if psiphon binary exists
if [ ! -f "/usr/local/bin/psiphon" ]; then
    echo "Psiphon binary not found. Downloading..."
    
    wget -O /usr/local/bin/psiphon \
        https://raw.githubusercontent.com/Psiphon-Labs/psiphon-tunnel-core-binaries/master/linux/psiphon-tunnel-core-x86_64 \
        --show-progress
    
    chmod +x /usr/local/bin/psiphon
    echo "✓ Psiphon binary downloaded"
fi

# Create psiphon user if doesn't exist
if ! id psiphon &>/dev/null; then
    echo "Creating psiphon user..."
    groupadd -rf psiphon
    useradd -r -g psiphon -s /usr/bin/nologin psiphon
    echo "✓ Psiphon user created"
fi

# Set ownership
chown root:psiphon /usr/local/bin/psiphon
chown -R psiphon:psiphon /etc/psiphon

# Enable and start service
echo ""
echo "Enabling Psiphon service..."
systemctl daemon-reload
systemctl enable psiphon.service
systemctl start psiphon.service

echo ""
echo "=========================================="
echo "  Psiphon VPN Setup Complete!"
echo "=========================================="
echo ""
echo "Psiphon is now running on:"
echo "  HTTP Proxy:  localhost:8081"
echo "  SOCKS Proxy: localhost:1081"
echo ""
echo "To use Psiphon with applications:"
echo "  export HTTP_PROXY=http://localhost:8081"
echo "  export HTTPS_PROXY=http://localhost:8081"
echo ""
echo "Or use the proxify wrapper:"
echo "  /usr/local/bin/proxify <command>"
echo ""
echo "Check status:"
echo "  systemctl status psiphon"
echo ""
echo "View logs:"
echo "  journalctl -u psiphon -f"
echo ""
