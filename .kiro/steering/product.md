# Product Overview

## What This Is

An automated Arch Linux installation system that creates a security-hardened desktop environment with Hyprland (Wayland compositor). The project combines beautiful, usable design (end-4's dotfiles) with enterprise-grade security features.

## Core Value Proposition

- **Zero-compromise security**: Defense-in-depth architecture with audit, firewall, sandboxing, and kernel hardening
- **Privacy-first networking**: DNS over TLS, optional VPN (Psiphon), MAC randomization
- **Automated maintenance**: Self-monitoring system with desktop notifications for security events, updates, and system health
- **Beautiful interface**: Modern Hyprland compositor with Material Design 3 theming and AI integration
- **Wayland-only**: X11 packages are actively blocked to maintain security posture

## Target Users

System administrators and security-conscious users who want:
- A hardened Linux desktop without manual configuration
- Real-time security monitoring with actionable notifications
- Automated system maintenance
- Modern, beautiful interface that doesn't compromise security

## Key Features

### Security
- **Audit system**: Real-time monitoring of sensitive file access, privilege escalation, rootkit behavior
- **Firewall**: Default-deny nftables configuration with group-based internet access control
- **Application sandboxing**: Automatic Firejail profiles for all applications
- **Kernel hardening**: Comprehensive sysctl parameters, hardened kernel
- **Encrypted storage**: Optional LUKS full-disk encryption

### Privacy
- DNS over TLS (Quad9, Cloudflare)
- Psiphon VPN for censorship circumvention
- MAC address randomization
- mDNS/LLMNR disabled

### Automation
- Daily package sync and update notifications
- Weekly security audits (CVE checks, permission audits, secure boot verification)
- Automatic reboot notifications for kernel updates
- USB auto-mount for encrypted drives
- Desktop notifications for all security events

### Desktop Environment
- Hyprland Wayland compositor
- Quickshell widget system (QtQuick-based)
- SDDM display manager
- end-4's beautiful dotfiles with AI integration

## Installation Approach

Two-phase installation:
1. **Base system** (installer.sh): Installs Arch Linux with security hardening
2. **Desktop environment** (install-hyprland-dots.sh): Installs Hyprland with end-4's dotfiles

Supports both encrypted and unencrypted installations with automatic configuration.
