# Project Structure

## Overview

The project follows a "configuration overlay" pattern where the `rootfs/` directory mirrors the target system's filesystem structure. During installation, these files are copied to the installed system to apply security hardening and custom configurations.

## Root Directory

```
.
├── installer.sh                    # Main installation script (Phase 1)
├── install-hyprland-dots.sh        # Hyprland dotfiles installer (Phase 2)
├── packages.cfg                    # Package definitions (PACKAGES and AUR arrays)
├── baseInstall.sh                  # Legacy installer (not actively used)
├── vpninstaller.sh                 # Psiphon VPN installer
├── setup-psiphon.sh                # Post-boot VPN setup
├── checkpack.sh                    # Package validation utility
├── detect-hardware.sh              # Hardware detection utility
├── test-notifications.sh           # Notification system testing
├── quick-notify-test.sh            # Quick notification test
├── proxy-control.txt               # Proxy configuration notes
├── README.md                       # Complete user documentation
├── QUICK_START.md                  # Fast installation guide
├── INSTALLATION_CHECKLIST.md       # Step-by-step checklist
├── PROJECT_SUMMARY.md              # Detailed project overview
├── ARCHITECTURE.md                 # System architecture diagrams
├── DNS_CONFIGURATION.md            # DNS setup documentation
└── rootfs/                         # System configuration overlay
```

## rootfs/ Directory Structure

The `rootfs/` directory contains all system configuration files that will be deployed to the installed system. It mirrors the Linux filesystem hierarchy:

### System Configuration (`rootfs/etc/`)

```
rootfs/etc/
├── audit/                          # Audit system configuration
│   ├── auditd.conf                # Audit daemon settings
│   └── rules.d/                   # Audit rules
│       ├── 00-reset.rules         # Clear previous rules
│       ├── 01-exclude.rules       # Exclude noisy events
│       ├── 10-files.rules         # Monitor sensitive files
│       └── 99-immutable.rules     # Lock rules (prevent tampering)
│
├── firejail/                       # Application sandboxing profiles
│   ├── firejail.config            # Global Firejail configuration
│   ├── globals.local              # Global overrides
│   ├── keepassxc.local            # KeePassXC-specific profile
│   └── signal-desktop.local       # Signal-specific profile
│
├── security/                       # PAM and security settings
│   └── faillock.conf              # Login failure handling (5 attempts, 5 min lockout)
│
├── sysctl.d/                       # Kernel parameters
│   └── 99-swappiness.conf         # System hardening (IPv6 disabled, ASLR, etc.)
│
├── iwd/                            # Wireless configuration
│   └── main.conf                  # iwd daemon settings
│
├── libvirt/                        # Virtualization configuration
│   ├── libvirtd.conf              # Libvirt daemon settings
│   └── qemu.conf                  # QEMU/KVM settings
│
├── psiphon/                        # VPN configuration
│   ├── psiphon.config             # Psiphon settings
│   └── ca.psiphon.PsiphonTunnel.tunnel-core/
│       ├── datastore/             # Psiphon data
│       ├── osl/                   # OSL data
│       └── remote_server_list     # Server list
│
├── pacman.d/hooks/                 # Pacman automation hooks
│   ├── pre-10-deny-xorg-packages.hook          # Block X11 packages
│   ├── post-20-dash-symlink.hook               # Maintain dash symlink
│   ├── post-20-firejail-hardening.hook         # Harden Firejail
│   ├── post-20-firejail-symlinks.hook          # Auto-configure Firejail
│   └── post-90-should-reboot-check.hook        # Reboot notifications
│
├── systemd/                        # Systemd configuration
│   ├── network/                   # Network configuration
│   │   ├── 70-wired.network       # Ethernet settings
│   │   └── 80-wireless.network    # WiFi settings
│   │
│   ├── resolved.conf.d/           # DNS configuration
│   │   └── default.conf_back      # DNS over TLS settings
│   │
│   ├── sleep.conf.d/              # Power management
│   │   └── disable-hibernate.conf # Disable hibernation
│   │
│   ├── system/                    # System services and timers
│   │   ├── auditd-notify.service              # Real-time audit notifications
│   │   ├── auditor.service                    # Security audit script
│   │   ├── auditor.timer                      # Weekly audit schedule
│   │   ├── check-secure-boot.service          # Secure boot verification
│   │   ├── local-forwarding-proxy.service     # Local proxy
│   │   ├── local-forwarding-proxy-vpn.service # VPN-enabled proxy
│   │   ├── pacman-notify.service              # Update notifications
│   │   ├── pacman-notify.timer                # Daily update check
│   │   ├── pacman-sync.service                # Background package sync
│   │   ├── pacman-sync.timer                  # Daily sync schedule
│   │   ├── psiphon.service                    # VPN service
│   │   ├── psiphon.timer                      # VPN restart timer
│   │   ├── randomize.service                  # MAC/hostname randomization
│   │   ├── randomize.timer                    # Randomization schedule
│   │   ├── should-reboot-check.service        # Reboot check
│   │   ├── should-reboot-check.timer          # Daily reboot check
│   │   ├── usb-auto-mount@.service            # USB auto-mount template
│   │   │
│   │   ├── dirmngr@etc-pacman.d-gnupg.service.d/
│   │   │   └── override.conf                  # Allow GPG internet access
│   │   ├── getty@tty1.service.d/
│   │   │   └── autologin.conf                 # Auto-login configuration
│   │   └── systemd-networkd-wait-online.service.d/
│   │       └── override.conf                  # Network wait settings
│   │
│   └── user/                      # User services
│       ├── gammastep.service      # Blue light filter
│       ├── journalctl-notify.service  # Log notifications
│       └── restic-unattended.timer    # Backup timer
│
├── udev/rules.d/                   # Device rules
│   └── 99-usb-auto-mount.rules    # USB auto-mount trigger
│
├── nftables.conf                   # Firewall rules (default-deny)
├── sudoers                         # Sudo configuration (hardened)
├── bash.bashrc                     # Global bash configuration
├── locale.conf                     # System locale
└── resolv.conf                     # DNS resolver configuration
```

### User Configuration (`rootfs/home/`)

```
rootfs/home/user/
└── .zshrc                          # Zsh configuration template
```

**Note**: The `user` directory is renamed to the actual username during installation.

### Custom Scripts (`rootfs/usr/local/bin/`)

All custom scripts and wrappers live here:

```
rootfs/usr/local/bin/
├── auditd-notify                   # Real-time audit log monitor (Python)
├── auditor                         # Security audit script (Python)
├── journalctl-notify               # Systemd journal monitor (Python)
├── send_notification.py            # Notification helper library (Python)
│
├── pacman-notify                   # Update notification script (Bash)
├── should-reboot-check             # Reboot check script (Bash)
├── notify-disk-error               # Disk error notifier (Bash)
├── notify-low-on-disk-space        # Low space notifier (Bash)
├── try-to-fix-low-on-disk-space    # Auto disk cleanup (Bash)
│
├── macchanger.py                   # MAC randomization (Python)
├── usb-auto-mount                  # USB mount handler (Bash)
├── usb_enable                      # USB enable script (Bash)
├── usb_kill                        # USB kill script (Bash)
├── usba                            # USB enable alias (Bash)
├── usbk                            # USB kill alias (Bash)
│
├── pacman                          # Pacman wrapper (proxy-aware) (Bash)
├── yay                             # Yay wrapper (proxy-aware) (Bash)
├── firefox                         # Firefox wrapper (arkenfox) (Bash)
├── proxify                         # Proxy wrapper utility (Bash)
└── proxy-mode                      # Proxy mode switcher (Bash)
```

## File Naming Conventions

### Scripts
- **Bash scripts**: No extension (e.g., `installer.sh` in root, but `auditd-notify` in `/usr/local/bin/`)
- **Python scripts**: Either `.py` extension or shebang-only (e.g., `macchanger.py` vs `auditd-notify`)
- **Executable**: All scripts in `/usr/local/bin/` are made executable during installation

### Configuration Files
- **Systemd services**: `.service` extension
- **Systemd timers**: `.timer` extension
- **Systemd overrides**: `override.conf` in `.d/` directories
- **Audit rules**: `.rules` extension with numeric prefix (e.g., `10-files.rules`)
- **Pacman hooks**: `.hook` extension with numeric prefix (e.g., `pre-10-deny-xorg-packages.hook`)

### Documentation
- **Markdown**: `.md` extension, UPPERCASE names for root-level docs (e.g., `README.md`, `ARCHITECTURE.md`)

## Key Architectural Patterns

### 1. Rootfs Overlay Pattern
Configuration files are organized in `rootfs/` to mirror the target filesystem, then copied wholesale during installation. This makes it easy to see what will be deployed.

### 2. Wrapper Scripts
Critical system commands (`pacman`, `yay`, `firefox`) are wrapped in `/usr/local/bin/` to add functionality (proxy support, security warnings) without modifying the original binaries.

### 3. Systemd Integration
Heavy use of systemd services and timers for automation:
- **Services**: One-shot or long-running daemons
- **Timers**: Scheduled tasks (daily, weekly)
- **Drop-ins**: Override configurations in `.d/` directories

### 4. Notification System
All monitoring scripts use a common notification format (JSON) piped to `send_notification.py`, which handles desktop notifications via libnotify/Dunst.

### 5. Security Layers
Defense-in-depth with multiple independent security mechanisms:
- **Network**: nftables firewall
- **Application**: Firejail sandboxing
- **System**: Audit monitoring
- **Kernel**: sysctl hardening

## Important Directories to Know

- **`/usr/local/bin/`**: Custom scripts (highest priority in PATH)
- **`/etc/systemd/system/`**: Custom services and timers
- **`/etc/audit/rules.d/`**: Audit rules (loaded in numeric order)
- **`/etc/pacman.d/hooks/`**: Pacman automation hooks
- **`/var/log/audit/`**: Audit logs
- **`~/.config/hypr/`**: Hyprland configuration (after Phase 2)
- **`~/.config/quickshell/`**: Widget configuration (after Phase 2)

## Configuration Precedence

1. **User-level**: `~/.config/` (highest priority)
2. **System-level**: `/etc/`
3. **Package defaults**: `/usr/share/`, `/usr/lib/`

For systemd, drop-in overrides in `.d/` directories take precedence over main configuration files.
