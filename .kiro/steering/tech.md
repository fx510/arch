# Technology Stack

## Operating System

- **Base**: Arch Linux
- **Kernel**: linux-hardened (security-focused kernel with additional hardening patches)
- **Init System**: systemd
- **Bootloader**: systemd-boot (UEFI only)
- **Boot Splash**: Plymouth (arch-charge theme)

## Desktop Environment

- **Compositor**: Hyprland (Wayland-only, tiling window manager)
- **Display Manager**: SDDM
- **Widget System**: Quickshell (QtQuick-based, from end-4/dots-hyprland)
- **Terminal**: Kitty
- **Shell**: Zsh with Oh-My-Zsh
- **File Manager**: Thunar
- **Notification Daemon**: Dunst

## Security Stack

- **Audit**: auditd (Linux Audit Framework)
- **Firewall**: nftables (default-deny policy)
- **Sandboxing**: Firejail (automatic application sandboxing)
- **Encryption**: LUKS2 (AES-256-XTS, SHA-512)
- **Volume Management**: LVM2 (when encryption is enabled)

## Network & Privacy

- **Network Manager**: NetworkManager
- **Wireless**: iwd (Intel Wireless Daemon)
- **DNS**: systemd-resolved with DNS over TLS
- **VPN**: Psiphon (censorship circumvention)
- **Proxy**: glider (local forwarding proxy)

## Programming Languages & Runtimes

- **Shell Scripts**: Bash (all installer scripts)
- **Python**: Python 3 (monitoring and notification scripts)
- **Rust**: Via rustup (required for some AUR packages)

## Package Management

- **Official Packages**: pacman
- **AUR Helper**: yay-bin
- **Custom Wrappers**: `/usr/local/bin/pacman` and `/usr/local/bin/yay` (proxy-aware wrappers)

## Key Libraries & Dependencies

- **Qt**: Qt5 and Qt6 with Wayland support
- **Audio**: PipeWire (with ALSA, PulseAudio, and JACK compatibility)
- **Graphics**: Mesa, Vulkan (Intel + NVIDIA support)
- **Python Libraries**: requests, pillow, pywal, gobject

## Build Tools

- **C/C++**: gcc, base-devel
- **Build Systems**: cmake, meson, ninja
- **Python**: pip (package installer)

## Common Commands

### Installation

```bash
# Run main installer (from Arch live USB)
./installer.sh

# After reboot, install Hyprland dotfiles
./install-hyprland-dots.sh
```

### Package Management

```bash
# Update system
yay -Syu

# Install package
yay -S package-name

# Search packages
yay -Ss search-term

# Remove package
yay -R package-name

# Clean package cache
yay -Sc
```

### Security Monitoring

```bash
# View audit logs
sudo ausearch -ts recent

# Check firewall status
sudo nft list ruleset

# View firewall logs
sudo journalctl -k | grep FIREWALL

# Run security audit manually
sudo /usr/local/bin/auditor

# Check audit daemon status
sudo systemctl status auditd
```

### System Services

```bash
# Enable/disable services
sudo systemctl enable service-name
sudo systemctl disable service-name

# Start/stop services
sudo systemctl start service-name
sudo systemctl stop service-name

# View service logs
journalctl -u service-name

# List failed services
systemctl --failed
```

### Network Management

```bash
# Connect to WiFi
nmcli device wifi connect SSID password PASSWORD

# List connections
nmcli connection show

# Enable/disable VPN
sudo systemctl start psiphon.service
sudo systemctl stop psiphon.service
```

### User Management

```bash
# Add user to allow-internet group (required for internet access)
sudo usermod -aG allow-internet username

# View user groups
groups username

# Add user to other groups
sudo usermod -aG wheel,audit,libvirt username
```

### Debugging

```bash
# View boot logs
journalctl -b

# View kernel messages
dmesg

# Check Hyprland logs
cat ~/.hyprland.log

# View systemd service logs
journalctl -xe

# Check disk usage
ncdu /
```

## Configuration Files

### Installer Configuration
- `installer.sh`: Main configuration variables (ROOT_DEV, USER, passwords, ENCRYPTED flag)
- `packages.cfg`: Package lists (PACKAGES array for official repos, AUR array for AUR packages)

### Security Configuration
- `/etc/audit/rules.d/`: Audit rules
- `/etc/nftables.conf`: Firewall rules
- `/etc/firejail/`: Firejail profiles
- `/etc/sysctl.d/99-swappiness.conf`: Kernel hardening parameters
- `/etc/sudoers`: Sudo configuration

### Network Configuration
- `/etc/systemd/network/`: Network interface configuration
- `/etc/systemd/resolved.conf.d/`: DNS over TLS configuration
- `/etc/iwd/main.conf`: Wireless configuration

### System Services
- `/etc/systemd/system/`: Custom systemd services and timers
- `/usr/local/bin/`: Custom scripts and wrappers

## Testing

No automated test suite exists. Testing is manual:

1. **Installation Testing**: Run installer.sh in a VM or test machine
2. **Security Testing**: Verify audit logs, firewall rules, and sandboxing
3. **Notification Testing**: Use `test-notifications.sh` to verify notification system
4. **Package Validation**: Use `checkpack.sh` to verify package list

## Build Process

The project uses a "rootfs overlay" approach:
1. Base system installed via pacstrap
2. Packages installed via pacman/yay
3. Configuration files copied from `rootfs/` directory to `/mnt/`
4. Scripts made executable and services enabled
5. Initramfs regenerated with security hooks

No compilation is required for the installer itself (pure bash scripts).
