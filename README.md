# Arch Linux Hyprland Installation with Security Hardening

This repository contains scripts to install a fully configured Arch Linux system with:
- **Hyprland** (Wayland compositor) with end-4's beautiful dotfiles
- **Security hardening** (audit, firewall, sandboxing)
- **Privacy features** (VPN, DNS over TLS, MAC randomization)
- **Automated maintenance** (update checks, notifications)

## 📋 Prerequisites

1. Boot from Arch Linux installation media
2. Connect to the internet
3. Partition your disk (or let the script handle it)

### Recommended Partitioning

**For encrypted setup:**
```bash
# EFI partition (512MB)
sgdisk -n 1:0:+512M -t 1:ef00 /dev/nvme0n1p1
mkfs.fat -F32 /dev/nvme0n1p1

# Root partition (rest of disk)
sgdisk -n 2:0:0 -t 2:8309 /dev/nvme0n1p2
```

**For unencrypted setup:**
```bash
# Single partition for everything
sgdisk -n 1:0:0 -t 1:8300 /dev/nvme0n1p1
```

## 🚀 Installation Steps

### Step 1: Configure installer.sh

Edit `installer.sh` and set your variables:

```bash
ROOT_DEV="/dev/nvme0n1p2"      # Your root partition
BOOT_DEV="/dev/nvme0n1p1"      # Boot partition (only if ENCRYPTED=true)
USER="yourusername"             # Your username
HOSTNAME="myhostname"           # Your hostname
ENCRYPTED=false                 # true for encryption, false for no encryption
```

Passwords are no longer hardcoded in the script. You have two secure options:

```bash
# Option A: interactive prompts (recommended)
./installer.sh

# Option B: environment variables (automation / CI)
ROOT_PASS='...' USER_PASS='...' LUKS_PASS='...' ./installer.sh
```

### Step 2: Run the installer

```bash
# Make the script executable
chmod +x installer.sh

# Run the installation
./installer.sh
```

The installer will:
- ✅ Set up disk encryption (if enabled)
- ✅ Install base system with hardened kernel
- ✅ Install all packages (Hyprland, security tools, etc.)
- ✅ Deploy security configurations from rootfs/
- ✅ Configure bootloader
- ✅ Set up users and groups
- ✅ Install AUR helper (yay)
- ✅ Install AUR packages

### Step 3: Reboot

```bash
reboot
```

### Step 4: Install Hyprland Dotfiles

After booting into your new system:

```bash
# Log in as your user
# Copy the installation files if needed
sudo cp -r /path/to/arch /home/yourusername/
sudo chown -R yourusername:yourusername /home/yourusername/arch

# Navigate to the directory
cd ~/arch

# Make the script executable
chmod +x install-hyprland-dots.sh

# Run the Hyprland dots installer
./install-hyprland-dots.sh
```

This will:
- Install Oh-My-Zsh
- Install Rust (required for some dependencies)
- Clone end-4/dots-hyprland
- Run the interactive installer
- Set up the beautiful Hyprland interface

### Step 5: Log into Hyprland

1. Log out of your session
2. At the SDDM login screen, select **Hyprland** from the session menu
3. Log in with your credentials
4. Enjoy your new setup!

## 🎨 Hyprland Features (end-4 dots)

- **Overview**: Shows open apps with live previews
- **AI Integration**: Gemini, Ollama support
- **QoL Features**: Screen translation, anti-flashbang, Google Lens
- **Material Themes**: Dynamic theming based on wallpaper
- **Transparent Installation**: Every command shown before execution

### Important Keybinds

- `Super + /` - Show keybind list
- `Super + Enter` - Open terminal
- `Super + Q` - Close window
- `Super + M` - Exit Hyprland
- `Super + Space` - App launcher

## 🔒 Security Features

### Audit System
- Monitors file access to sensitive files (`/etc/shadow`, secure boot keys)
- Detects privilege escalation attempts
- Tracks rootkit-like behavior
- Sends desktop notifications for security events

### Firewall (nftables)
- Default-deny policy
- Group-based internet access (`allow-internet` group)
- Logs all rejected connections
- Supports libvirt/docker

### Application Sandboxing (Firejail)
- Automatic sandboxing for applications
- Custom profiles for sensitive apps
- Reduces attack surface

### System Hardening
- Kernel hardening parameters (sysctl)
- Disabled IPv6
- Protection against IP spoofing, SYN floods
- Restricted kernel pointers, BPF, ptrace

### Network Privacy
- DNS over TLS (Quad9, Cloudflare)
- DNSSEC enabled
- mDNS and LLMNR disabled
- MAC address randomization (optional)

### VPN Support
- Psiphon VPN for censorship circumvention
- Automatic proxy configuration

## 📦 Installed Software

### Desktop Environment
- Hyprland (Wayland compositor)
- Quickshell (widget system)
- SDDM (display manager)
- Kitty (terminal)

### Applications
- Firefox (browser)
- Thunar (file manager)
- MPV (media player)
- Dunst (notifications)

### Development
- Git, base-devel
- Python with pip
- Rust (via rustup)

### Security Tools
- Audit (system monitoring)
- Firejail (sandboxing)
- nftables (firewall)

## 🛠️ Post-Installation Configuration

### Enable User Services

```bash
# As your user
systemctl --user enable gammastep.service
systemctl --user enable journalctl-notify.service
```

### Configure Firewall

To allow a user internet access:
```bash
sudo usermod -aG allow-internet yourusername
```

### Configure VPN (Psiphon)

The Psiphon service is installed but not enabled by default:
```bash
sudo systemctl enable psiphon.service
sudo systemctl start psiphon.service
```

### USB Auto-Mount

Encrypted USB drives listed in `/etc/crypttab` will auto-mount when plugged in.

## 📁 File Structure

```
.
├── installer.sh                    # Main installation script
├── baseInstall.sh                  # Legacy installer (not used)
├── packages.cfg                    # Package list
├── install-hyprland-dots.sh        # Post-install Hyprland setup
├── vpninstaller.sh                 # Psiphon VPN installer
├── checkpack.sh                    # Package validation script
└── rootfs/                         # System configuration overlay
    ├── etc/
    │   ├── audit/                  # Audit rules
    │   ├── firejail/               # Firejail profiles
    │   ├── nftables.conf           # Firewall rules
    │   ├── pacman.d/hooks/         # Pacman hooks
    │   ├── psiphon/                # VPN config
    │   ├── security/               # PAM config
    │   ├── sudoers                 # Sudo configuration
    │   ├── sysctl.d/               # Kernel parameters
    │   ├── systemd/                # Services & timers
    │   └── udev/                   # USB auto-mount rules
    ├── home/user/                  # User home template
    └── usr/local/bin/              # Custom scripts
```

## 🔧 Customization

### Change Display Manager Theme

SDDM themes can be configured in `/etc/sddm.conf.d/`

### Modify Hyprland Configuration

After installing end-4 dots, configs are in:
- `~/.config/hypr/` - Hyprland config
- `~/.config/quickshell/` - Widget system

### Adjust Security Settings

- Audit rules: `/etc/audit/rules.d/`
- Firewall: `/etc/nftables.conf`
- Sysctl: `/etc/sysctl.d/99-swappiness.conf`

## 🐛 Troubleshooting

### Boot Issues

Check boot logs:
```bash
journalctl -b
```

### Hyprland Won't Start

Check Hyprland logs:
```bash
cat ~/.hyprland.log
```

### Missing Dependencies

Reinstall packages:
```bash
yay -S --needed $(cat packages.cfg | grep -v '^#' | grep -v '^$')
```

### Firewall Blocking Everything

Temporarily disable:
```bash
sudo systemctl stop nftables
```

Add your user to allow-internet group:
```bash
sudo usermod -aG allow-internet $USER
```

## 📚 Resources

- [Hyprland Wiki](https://wiki.hyprland.org/)
- [end-4 dots-hyprland](https://github.com/end-4/dots-hyprland)
- [Arch Wiki](https://wiki.archlinux.org/)
- [Firejail Documentation](https://firejail.wordpress.com/)

## 📝 Notes

- This is a **Wayland-only** system. X11 packages are blocked by pacman hooks.
- The system uses **systemd-boot** as the bootloader.
- **Plymouth** is configured for boot splash screens.
- All custom scripts are in `/usr/local/bin/`.

## ⚠️ Important Security Considerations

1. **Never hardcode passwords** in `installer.sh`; use prompts or environment variables
2. **Review firewall rules** in `rootfs/etc/nftables.conf`
3. **Check audit rules** in `rootfs/etc/audit/rules.d/`
4. **Enable Secure Boot** in your BIOS/UEFI after installation
5. **Keep your system updated**: `yay -Syu`

## 🤝 Contributing

Feel free to submit issues or pull requests for improvements!

## 📄 License

This configuration is provided as-is. Use at your own risk.

---

**Enjoy your new Arch Linux + Hyprland system! 🎉**
