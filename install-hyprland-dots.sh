#!/bin/bash
# Post-installation script to install end-4 Hyprland dots
# Run this AFTER the base system installation is complete and you've rebooted

set -euo pipefail

USER_NAME="${1:-aymen}"  # Default to aymen, or pass username as argument

echo "=========================================="
echo "  end-4 Hyprland Dots Installation"
echo "=========================================="
echo ""
echo "This script will install end-4's Hyprland dotfiles"
echo "User: $USER_NAME"
echo ""

# Check if running as the target user
if [ "$(whoami)" != "$USER_NAME" ]; then
    echo "Error: This script should be run as user '$USER_NAME'"
    echo "Usage: su - $USER_NAME -c './install-hyprland-dots.sh'"
    exit 1
fi

# Ensure we're in the home directory
cd ~

echo "Step 1: Installing Oh-My-Zsh (if not already installed)..."
if [ ! -d "$HOME/.oh-my-zsh" ]; then
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
    echo "Oh-My-Zsh installed successfully"
else
    echo "Oh-My-Zsh already installed, skipping..."
fi

echo ""
echo "Step 2: Installing Rust (required for some dependencies)..."
if ! command -v rustc &> /dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
    echo "Rust installed successfully"
else
    echo "Rust already installed, skipping..."
fi

echo ""
echo "Step 3: Cloning end-4/dots-hyprland repository..."
if [ -d "$HOME/dots-hyprland" ]; then
    echo "Repository already exists. Updating..."
    cd "$HOME/dots-hyprland"
    git pull
else
    git clone https://github.com/end-4/dots-hyprland.git "$HOME/dots-hyprland"
    cd "$HOME/dots-hyprland"
fi

echo ""
echo "Step 4: Running the end-4 installation script..."
echo "=========================================="
echo "IMPORTANT: The installer will show you every command before running it."
echo "Review each command carefully and approve as needed."
echo "=========================================="
echo ""
read -p "Press Enter to continue with the installation..."

# Run the setup script
./setup install

echo ""
echo "=========================================="
echo "  Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Log out of your current session"
echo "2. Select 'Hyprland' from your display manager (SDDM)"
echo "3. Log in and enjoy your new setup!"
echo ""
echo "Important keybinds:"
echo "  Super + /        = Show keybind list"
echo "  Super + Enter    = Open terminal"
echo "  Super + Q        = Close window"
echo "  Super + M        = Exit Hyprland"
echo ""
echo "For more information, visit:"
echo "  https://github.com/end-4/dots-hyprland"
echo ""
