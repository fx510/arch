#!/usr/bin/env bash
# =============================================================================
# test.sh — deploy nftables config and test
# =============================================================================
set -euo pipefail

# ── Deploy ────────────────────────────────────────────────────────────────────
echo "==> Deploying nftables config..."
sudo cp -f etc/nftables.conf /etc/nftables.conf
sudo nft -c -f /etc/nftables.conf && echo "✓ Syntax OK" || exit 1
sudo systemctl restart nftables.service
sudo systemctl enable nftables.service

echo ""
echo "==> nftables status:"
sudo systemctl status nftables.service --no-pager || true

echo ""
echo "==> Active rules (OUTPUT chain):"
sudo nft list chain inet filter output | tail -20

echo ""
echo "==> Done. Firewall is active with:"
echo "    - Default-deny on all chains"
echo "    - UID 1000 (aymen) allowed (DEV ONLY)"
echo "    - allow-internet group allowed"
echo "    - All other users/processes blocked"

