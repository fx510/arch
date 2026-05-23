#!/bin/bash
set -euo pipefail  # Exit on errors, undefined vars, pipe failures

## VAR 
ROOT_DEV="/dev/nvme0n1p51"
BOOT_DEV="/dev/nvme0n1p43"        # Only used if ENCRYPTED=true
USER="test"
USER_PASS="asdasd"
ROOT_PASS="test"
LUKS_PASS="asdasd"	             # LUKS encrypted password (only used if ENCRYPTED=true)
HOSTNAME="archyBTW"	             # Hostname
ENCRYPTED=true                   # Set to false for unencrypted installation (no separate boot partition)

# MKMODULES="i915"
PACKAGE_FILE="packages.cfg"

# Log file for debugging
LOG_FILE="/tmp/arch_install_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

run_command() {
    "$@"  
    # Check if the command failed
    if [ $? -ne 0 ]; then
        # Print the error message in red
        echo -e "Error: Command failed : $@ "
        # Exit on critical failures to prevent continuing with broken state
        exit 1
    fi
}

# Input validation function
validate_setup() {
    echo "Validating setup..."
    [ -b "$ROOT_DEV" ] || { echo "Root device $ROOT_DEV not found"; exit 1; }
    
    # Only check BOOT_DEV if encryption is enabled
    if [ "$ENCRYPTED" = true ]; then
        [ -b "$BOOT_DEV" ] || { echo "Boot device $BOOT_DEV not found (required for encrypted setup)"; exit 1; }
    fi
    
    [ -f "$PACKAGE_FILE" ] || { echo "Package file $PACKAGE_FILE not found"; exit 1; }
    [ -d /sys/firmware/efi ] || { echo "System not booted in UEFI mode"; exit 1; }
    
    if [ "$ENCRYPTED" = true ] && [ -z "$LUKS_PASS" ]; then
        echo "Error: LUKS_PASS cannot be empty when ENCRYPTED=true"
        exit 1
    fi
    
    echo "Setup validation passed."
}

# Cleanup function for trap
cleanup() {
    echo "Cleaning up on exit..."
    umount -R /mnt 2>/dev/null || true
    if [ "$ENCRYPTED" = true ]; then
        vgchange -an vg0 2>/dev/null || true
        cryptsetup close /dev/mapper/archy 2>/dev/null || true
    fi
}

# Set trap for cleanup on exit
trap cleanup EXIT

# Run validation
validate_setup

echo "Starting Arch Linux installation..."
echo "Encryption: $ENCRYPTED"
echo "Target device: $ROOT_DEV"
if [ "$ENCRYPTED" = true ]; then
    echo "Boot device: $BOOT_DEV"
else
    echo "Boot device: Not used (integrated with root)"
fi

if [ "$ENCRYPTED" = true ]; then
    echo "Setting up encrypted installation..."
    
    # Set up LUKS on the root partition
    echo -n "$LUKS_PASS" | cryptsetup luksFormat "$ROOT_DEV" --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --use-random -

    # Open LUKS partition
    echo -n "$LUKS_PASS" | cryptsetup open "$ROOT_DEV" archy -

    ## Create LVM on encrypted partition
    run_command pvcreate /dev/mapper/archy
    run_command vgcreate vg0 /dev/mapper/archy
    run_command lvcreate --name root --extents 100%FREE vg0

    # Format and mount encrypted root
    run_command mkfs.ext4 /dev/vg0/root
    run_command mount /dev/vg0/root /mnt
    
    # Mount separate boot partition for encrypted setup
    run_command mkdir /mnt/boot 
    echo "mounting boot $BOOT_DEV for encrypted setup" 
    sleep 2
    run_command mount $BOOT_DEV /mnt/boot
    
    ROOT_MOUNT="/dev/vg0/root"
    BOOT_PATH="/boot"
    
else
    echo "Setting up unencrypted installation..."
    
    # Format root partition directly (no encryption, no separate boot)
    run_command mkfs.ext4 "$ROOT_DEV"
    run_command mount "$ROOT_DEV" /mnt
    
    # No separate boot partition - everything goes on root
    # Boot files will be at /boot on the root filesystem
    
    ROOT_MOUNT="$ROOT_DEV"
    BOOT_PATH="/boot"  # This will be a directory on root filesystem, not a separate mount
    
    echo "Using integrated boot (no separate boot partition)"
fi

# Create boot loader entries directory
run_command mkdir -p /mnt/boot/loader/entries/

# Install base system
run_command pacstrap -K /mnt base base-devel linux-hardened linux-firmware nano sudo networkmanager git plymouth

# Add LVM2 only if encrypted
if [ "$ENCRYPTED" = true ]; then
    run_command pacstrap -K /mnt lvm2
fi

# Generate fstab
run_command genfstab -U /mnt >> /mnt/etc/fstab

# Configure timezone
run_command arch-chroot /mnt ln -s /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime
run_command arch-chroot /mnt hwclock --systohc

# Configure locales
run_command arch-chroot /mnt bash -c "echo 'en_US.UTF-8 UTF-8' >> /etc/locale.gen"
run_command arch-chroot /mnt bash -c "echo 'ar_SA.UTF-8 UTF-8' >> /etc/locale.gen"

run_command arch-chroot /mnt locale-gen
run_command arch-chroot /mnt bash -c "echo 'LANG=en_US.UTF-8' > /etc/locale.conf"

# Configure console
run_command arch-chroot /mnt bash -c "echo 'KEYMAP=us' > /etc/vconsole.conf"

# Configure hostname
run_command arch-chroot /mnt bash -c "echo $HOSTNAME > /etc/hostname"

# Configure /etc/hosts file
run_command arch-chroot /mnt bash -c "cat <<EOL > /etc/hosts
127.0.0.1    localhost
::1          localhost
127.0.1.1    $HOSTNAME.localdomain 
EOL"

# Set passwords
run_command arch-chroot /mnt bash -c "echo 'root:$ROOT_PASS' | chpasswd"

# Create user
run_command arch-chroot /mnt useradd -m -s /bin/bash $USER
run_command arch-chroot /mnt bash -c "echo '$USER:$USER_PASS' | chpasswd"

# Add user to groups
for group in wheel audit libvirt firejail; do
    run_command arch-chroot /mnt groupadd -rf "$group"
    run_command arch-chroot /mnt gpasswd -a "$USER" "$group"
done

run_command arch-chroot /mnt groupadd -rf allow-internet

# Configure mkinitcpio based on encryption
if [ "$ENCRYPTED" = true ]; then
    echo "Configuring mkinitcpio for encrypted setup..."
    ## edit mkinitcpio.conf to include lvm2 and systemd boot for encryption
    run_command arch-chroot /mnt sed -i 's/^HOOKS.*/HOOKS=(base systemd plymouth autodetect modconf block sd-encrypt lvm2 filesystems keyboard fsck)/' /etc/mkinitcpio.conf
    
    ## Add entry for systemd (encrypted)
    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch.conf
title   $HOSTNAME System (Encrypted)
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened.img
options rd.luks.name=$(blkid -s UUID -o value "$ROOT_DEV")=archy root=/dev/vg0/root rw quiet splash rd.luks.options=discard,timeout=10
EOL"

    ## Add fallback entry (encrypted)
    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch-fallback.conf
title   $HOSTNAME System (Encrypted Fallback)
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened-fallback.img
options rd.luks.name=$(blkid -s UUID -o value "$ROOT_DEV")=archy root=/dev/vg0/root rw
EOL"

else
    echo "Configuring mkinitcpio for unencrypted setup..."
    ## edit mkinitcpio.conf for standard setup (no encryption hooks)
    run_command arch-chroot /mnt sed -i 's/^HOOKS.*/HOOKS=(base systemd plymouth autodetect modconf block filesystems keyboard fsck)/' /etc/mkinitcpio.conf
    
    ## Add entry for systemd (unencrypted)
    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch.conf
title   $HOSTNAME System
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened.img
options root=UUID=$(blkid -s UUID -o value "$ROOT_DEV") rw quiet splash
EOL"

    ## Add fallback entry (unencrypted)
    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch-fallback.conf
title   $HOSTNAME System (Fallback)
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened-fallback.img
options root=UUID=$(blkid -s UUID -o value "$ROOT_DEV") rw
EOL"
fi

# Configure bootloader
run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/loader.conf
default  arch.conf
timeout  5
console-mode max
editor   no
EOL"

# Check if PACKAGE_FILE is defined and exists
if [ -z "$PACKAGE_FILE" ]; then
    echo "Error: PACKAGE_FILE variable is not set."
    exit 1
fi

if [ ! -f "$PACKAGE_FILE" ]; then
    echo "Error: PACKAGE_FILE '$PACKAGE_FILE' does not exist."
    exit 1
fi

# Source the package configuration file
source "$PACKAGE_FILE"

# Check if PACKAGES array is defined and has packages
if [[ -z "${PACKAGES[@]}" || ${#PACKAGES[@]} -eq 0 ]]; then
    echo "No packages to install in PACKAGES array."
else 
    # Update the package database and install packages
    for package in "${PACKAGES[@]}"; do
        if ! run_command arch-chroot /mnt pacman --noconfirm --needed -S "$package"; then
            echo "Failed to install $package"
        else
            echo "Successfully installed $package."
        fi
    done
fi

# Enable NetworkManager
run_command arch-chroot /mnt systemctl enable NetworkManager

# Temporarily allow sudo without password for yay setup
run_command arch-chroot /mnt bash -c "echo '$USER ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers"

# Deploy rootfs_clean overlay (hardened configs, scripts, services)
echo "Deploying rootfs_clean overlay..."
if [ -d "rootfs_clean" ]; then
    run_command cp -r rootfs_clean/* /mnt/
    echo "✓ rootfs_clean overlay deployed"
    
    # Make scripts executable
    run_command chmod +x /mnt/usr/local/bin/* 2>/dev/null || true
    
    # Replace USER_ID placeholder in scripts with actual UID
    USER_UID=$(arch-chroot /mnt id -u "$USER")
    run_command sed -i "s/USER_ID = 1000/USER_ID = $USER_UID/" /mnt/usr/local/bin/audit_notify.py 2>/dev/null || true
    
    echo "✓ Scripts configured for user $USER (UID $USER_UID)"
else
    echo "Warning: rootfs_clean directory not found - skipping overlay deployment"
fi

# Setup firejail
run_command arch-chroot /mnt /usr/bin/firecfg
run_command sed -i "s/USER_PLACEHOLDER/$USER/" /mnt/etc/firejail/firejail.users

# Create kernel directory and configure cmdline
run_command arch-chroot /mnt mkdir -p /etc/kernel
{
  echo -n "lsm=landlock,lockdown,yama,integrity,apparmor,bpf "
  echo -n "lockdown=integrity "
  echo -n "mem_sleep_default=deep "
  echo -n "audit=1 audit_backlog_limit=32768 "
  echo -n "quiet splash rd.udev.log_level=3"
} > /mnt/etc/kernel/cmdline

## install Systemd Bootloader 
run_command arch-chroot /mnt bootctl install

# Configure plymouth
run_command arch-chroot /mnt plymouth-set-default-theme -R arch-charge

# Remove sudo NOPASSWD rights from user
run_command arch-chroot /mnt sed -i '$ d' /etc/sudoers

## install YAY
run_command arch-chroot -u $USER /mnt /bin/bash -c 'cd /tmp && \
                                          git clone https://aur.archlinux.org/yay-bin.git && \
                                          cd yay-bin && \
                                          makepkg -si --noconfirm'

# Install AUR packages if array exists
if [[ -n "${AUR[@]}" && ${#AUR[@]} -gt 0 ]]; then
    # Install each AUR package in the AUR array from packages.cfg
    for aurpkg in "${AUR[@]}"; do
        echo "Installing $aurpkg ..."
        if ! run_command arch-chroot /mnt su - $USER -c "yay --noconfirm -S $aurpkg" ; then
            echo "Failed to install $aurpkg. Continuing with the next package..."
        else
            echo "Successfully installed $aurpkg."
        fi
    done
else
    echo "No AUR packages to install."
fi
 
## Regenerate initramfs
run_command arch-chroot /mnt mkinitcpio -P

## Verification
echo "Verifying installation..."

# Check encryption setup
if [ "$ENCRYPTED" = true ]; then
    if ! blkid "$ROOT_DEV" | grep -q "crypto_LUKS"; then
        echo "Warning: LUKS partition verification failed"
    else
        echo "✓ LUKS encryption verified"
        echo "✓ Separate boot partition used: $BOOT_DEV"
    fi
else
    echo "✓ Unencrypted installation verified"
    echo "✓ Integrated boot (no separate boot partition)"
fi

# Check boot entry
if [ ! -f "/mnt/boot/loader/entries/arch.conf" ]; then
    echo "Warning: Boot entry not found"
else
    echo "✓ Boot entry created successfully"
fi

echo "Installation complete!"
echo "Encryption: $ENCRYPTED"
if [ "$ENCRYPTED" = true ]; then
    echo "Boot partition: $BOOT_DEV (separate)"
else
    echo "Boot partition: Integrated with root filesystem"
fi
echo "Log saved to: $LOG_FILE"

# Copy Hyprland installer to user's home directory for post-reboot setup
if [ -f "install-hyprland-dots.sh" ]; then
    run_command cp install-hyprland-dots.sh /mnt/home/$USER/
    run_command chown $(arch-chroot /mnt id -u $USER):$(arch-chroot /mnt id -g $USER) /mnt/home/$USER/install-hyprland-dots.sh
    run_command chmod +x /mnt/home/$USER/install-hyprland-dots.sh
    echo ""
    echo "=========================================="
    echo "  POST-REBOOT SETUP"
    echo "=========================================="
    echo "After rebooting, log in as '$USER' and run:"
    echo "  cd ~"
    echo "  ./install-hyprland-dots.sh"
    echo ""
    echo "This will install end-4's Hyprland dotfiles."
    echo "=========================================="
fi

echo ""
echo "Please verify the installation before rebooting."
echo "You can reboot now with: reboot"

