---
inclusion: auto
---

# Arch Linux + Hyprland Installation Project Steering

## Project Overview

This is an automated Arch Linux installation system with Hyprland desktop environment and comprehensive security hardening. The project consists of installation scripts, configuration overlays (rootfs), and post-installation setup.

## Key Principles

### 1. No Documentation Files
- **NEVER** create markdown documentation files (README, GUIDE, SUMMARY, etc.)
- **NEVER** create documentation unless explicitly requested by user
- **NEVER** create summary files or project overviews
- Focus ONLY on functional code and configuration files
- Keep explanations in code comments only
- User will ask if they need documentation

### 2. Installation Order is Critical
The installation must follow this exact order:
1. Base system installation
2. Official packages installation
3. **YAY AUR helper installation**
4. **AUR packages installation** (quickshell-git, etc.)
5. **Rootfs deployment** (MUST be after yay/AUR - contains wrapper scripts)
6. Service enablement
7. Reboot
8. Hyprland dots installation

**Why**: Rootfs contains wrapper scripts in `/usr/local/bin/` (pacman, yay, firefox) that override the real binaries. If deployed before yay installation, the wrapper will exist but the real yay binary won't, causing failures.

### 3. Security Architecture
- **Defense in depth**: Multiple security layers
- **Default deny**: Firewall blocks everything except explicitly allowed
- **Group-based access**: `allow-internet` group controls network access
- **Application sandboxing**: Firejail wraps all applications
- **System monitoring**: Auditd tracks security events
- **Real-time notifications**: Desktop alerts for security events

### 4. DNS Configuration
- **Default**: Use DHCP-provided DNS (works on any network)
- **No forced DNS**: Don't force Quad9 or any specific DNS
- **DNS over TLS**: Opportunistic mode (use when available)
- **User choice**: Users can configure custom DNS if they want

## File Structure

```
.
├── installer.sh              # Main installation script
├── packages.cfg              # Package list (Hyprland-focused)
├── install-hyprland-dots.sh  # Post-install Hyprland setup
├── vpninstaller.sh           # Psiphon VPN installer
├── setup-psiphon.sh          # Post-boot VPN setup
├── checkpack.sh              # Package validation
└── rootfs/                   # System configuration overlay
    ├── etc/
    │   ├── audit/            # Audit system
    │   ├── firejail/         # Sandboxing profiles
    │   ├── nftables.conf     # Firewall rules
    │   ├── pacman.d/hooks/   # Pacman automation
    │   ├── psiphon/          # VPN config
    │   ├── security/         # PAM config
    │   ├── sysctl.d/         # Kernel hardening
    │   ├── systemd/          # Services & timers
    │   └── udev/             # Device rules
    └── usr/local/bin/        # Custom scripts (wrappers, monitors)
```

## Critical Components

### installer.sh Variables
```bash
ROOT_DEV="/dev/nvme0n1p6"      # Root partition
BOOT_DEV="/dev/nvme0n1p7"      # Boot partition (if ENCRYPTED=true)
USER="aymen"                    # Username
USER_PASS="Aymen9988"          # User password
ROOT_PASS="aymen8899"          # Root password
LUKS_PASS="asdasd"             # Encryption password
HOSTNAME="android"              # Hostname
ENCRYPTED=false                 # Encryption toggle
```

### Rootfs Deployment
- Copies all files from `rootfs/*` to `/mnt/`
- Replaces `username_placeholder` with actual username
- Sets executable permissions on scripts
- Creates psiphon user/group
- **Must happen AFTER yay/AUR installation**

### Custom Scripts in /usr/local/bin/
- **Wrappers**: `pacman`, `yay`, `firefox` (proxy integration, warnings)
- **Monitors**: `auditd-notify`, `journalctl-notify`, `auditor`
- **Utilities**: `proxify`, `usb-auto-mount`, `macchanger.py`
- **Notifiers**: `should-reboot-check`, `pacman-notify`, disk space alerts

### Security Services
- `auditd.service` - Audit daemon
- `auditd-notify.service` - Real-time security notifications
- `auditor.timer` - Weekly security audits
- `nftables.service` - Firewall
- `local-forwarding-proxy.service` - Local proxy (glider)
- `psiphon.service` - VPN (optional)

### Automation Services
- `pacman-sync.timer` - Daily background package cache update
- `pacman-notify.timer` - Daily update notifications
- `should-reboot-check.timer` - Daily reboot check (kernel updates)
- `randomize.timer` - MAC/hostname randomization (optional)

## Common Tasks

### Adding a New Package
1. Edit `packages.cfg`
2. Add to `PACKAGES=()` array for official repos
3. Add to `AUR=()` array for AUR packages
4. Test with `./checkpack.sh packages.cfg`

### Adding a New Service
1. Create service file in `rootfs/etc/systemd/system/`
2. Create corresponding script in `rootfs/usr/local/bin/` if needed
3. Add enable command in `installer.sh` (after rootfs deployment)

### Adding a New Audit Rule
1. Create rule file in `rootfs/etc/audit/rules.d/`
2. Use naming: `##-description.rules` (## = order number)
3. Test syntax before deployment

### Modifying Firewall Rules
1. Edit `rootfs/etc/nftables.conf`
2. Test with: `nft -c -f rootfs/etc/nftables.conf`
3. Remember: Default deny policy, explicit allow needed

### Adding a Firejail Profile
1. Create profile in `rootfs/etc/firejail/appname.local`
2. Firecfg will auto-create symlinks on package install
3. Test with: `firejail --profile=/etc/firejail/appname.local appname`

## Troubleshooting Patterns

### Installation Fails at YAY
- Check if rootfs was deployed before yay installation
- Wrapper scripts in `/usr/local/bin/` interfere with installation
- **Solution**: Move rootfs deployment after AUR packages

### Firewall Blocks Everything
- User not in `allow-internet` group
- **Solution**: `sudo usermod -aG allow-internet $USER`

### Hyprland Won't Start
- Check logs: `cat ~/.hyprland.log`
- Verify quickshell-git installed: `pacman -Q quickshell-git`
- Check if end-4 dots installed: `ls ~/.config/hypr/`

### DNS Not Working
- Check resolved status: `resolvectl status`
- Verify network config: `/etc/systemd/network/`
- Check if DNS forced: `/etc/systemd/resolved.conf.d/`

### Package Installation Warnings
- Wrapper scripts warn before installing packages
- This is intentional (keep system clean)
- Answer 'y' to proceed if needed

## Code Style

### Shell Scripts
- Use `set -euo pipefail` for safety
- Use `run_command` wrapper for error handling
- Log with `log_info`, `log_error`
- Use progress bars for long operations

### Configuration Files
- Comment all non-obvious settings
- Include references to documentation
- Use descriptive variable names
- Keep security-sensitive values separate

### Python Scripts
- Use type hints
- Add docstrings for functions
- Handle errors gracefully
- Use subprocess for system commands

## Testing Checklist

Before committing changes:
- [ ] Test installation in VM
- [ ] Verify boot process
- [ ] Check all services start
- [ ] Test firewall rules
- [ ] Verify Hyprland starts
- [ ] Test security notifications
- [ ] Check audit logs

## Known Issues

1. **DNSSEC**: Not fully functional (systemd-resolved limitation)
2. **X11 Blocked**: Pacman hook prevents X11 packages (intentional)
3. **Wrapper Warnings**: Pacman/yay warn before installation (intentional)
4. **Quickshell Compilation**: Takes time during installation (normal)

## Future Improvements

- Add AppArmor profiles (currently commented out)
- Implement automatic backup system
- Add more firejail profiles
- Create custom SDDM theme
- Add TPM2 support for encryption
- Automate secure boot setup

## Important Notes

- **Never deploy rootfs before yay installation**
- **Always test in VM before real hardware**
- **Keep security configurations strict by default**
- **Document security decisions in code comments**
- **NEVER create documentation files unless user explicitly asks**
- **Focus on code, not documentation**

## Quick Reference

### File Locations
- Firewall: `/etc/nftables.conf`
- Audit rules: `/etc/audit/rules.d/`
- Firejail: `/etc/firejail/`
- Services: `/etc/systemd/system/`
- Scripts: `/usr/local/bin/`
- Network: `/etc/systemd/network/`
- DNS: `/etc/systemd/resolved.conf.d/`

### Key Commands
```bash
# Check services
systemctl --failed

# Check firewall
sudo nft list ruleset

# Check audit
sudo ausearch -ts recent

# Check DNS
resolvectl status

# Update system
yay -Syu
```

---

**Remember**: This is a security-focused system. Keep defaults strict, make users explicitly enable features, and always prioritize security over convenience.
