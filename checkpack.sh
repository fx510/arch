#!/bin/bash
# check-packages.sh
# Usage: ./check-packages.sh packages.cfg

set -euo pipefail

# Load packages.cfg
if [ $# -eq 0 ]; then
    echo "Usage: $0 <packages.cfg>"
    exit 1
fi

PACKAGE_FILE="$1"
if [ ! -f "$PACKAGE_FILE" ]; then
    echo "File not found: $PACKAGE_FILE"
    exit 1
fi

source "$PACKAGE_FILE"

# Function to check package
check_package() {
    local pkg="$1"
    if pacman -Si "$pkg" &>/dev/null; then
        echo "✓ $pkg exists in repo"
    else
        echo "✗ $pkg NOT found in repo"
    fi
}

echo "Checking official repository packages..."
for pkg in "${PACKAGES[@]}"; do
    check_package "$pkg"
done

echo
echo "Checking AUR packages (optional)..."
for aurpkg in "${AUR[@]}"; do
    # Simple check via yay (if installed)
    if command -v yay &>/dev/null; then
        if yay -Ss "^$aurpkg\$" &>/dev/null; then
            echo "✓ $aurpkg exists in AUR"
        else
            echo "✗ $aurpkg NOT found in AUR"
        fi
    else
        echo "AUR check skipped for $aurpkg (yay not installed)"
    fi
done
