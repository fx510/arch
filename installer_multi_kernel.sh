#!/bin/bash
set -euo pipefail  # Exit on errors, undefined vars, pipe failures

## VAR 
ROOT_DEV="/dev/nvme0n1p51"          # Root partition (LUKS container if ENCRYPTED=true)
BOOT_DEV="/dev/nvme0n1p43"          # EFI System Partition (ESP) – always required for UEFI
USER="test"
USER_PASS="asdasd"
ROOT_PASS="test"
LUKS_PASS="asdasd"                  # Only used when ENCRYPTED=true
HOSTNAME="archyBTW"
ENCRYPTED=true                      # true  = LUKS + LVM on ROOT_DEV; false = plain ext4 on ROOT_DEV

PACKAGE_FILE="packages.cfg"

# Kernel parameters – hardened vs standard
HARDENED_PARAMS="lsm=landlock,lockdown,yama,integrity,apparmor,bpf lockdown=integrity mem_sleep_default=deep audit=1 audit_backlog_limit=32768 quiet splash rd.udev.log_level=3"
STANDARD_PARAMS="quiet splash rd.udev.log_level=3"

# Logging
LOG_FILE="/tmp/arch_install_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

## Helper function – runs a command, exits with red error on failure
run_command() {
    "$@" || {
        echo -e "\e[31mError: Command failed: $*\e[0m" >&2
        exit 1
    }
}

# Validation
validate_setup() {
    echo "Validating setup..."
    [ -b "$ROOT_DEV" ] || { echo "Root device $ROOT_DEV not found"; exit 1; }
    [ -b "$BOOT_DEV" ]  || { echo "EFI boot device $BOOT_DEV not found"; exit 1; }

    [ -f "$PACKAGE_FILE" ] || { echo "Package file $PACKAGE_FILE not found"; exit 1; }
    [ -d /sys/firmware/efi ] || { echo "System not booted in UEFI mode"; exit 1; }

    if [ "$ENCRYPTED" = true ] && [ -z "$LUKS_PASS" ]; then
        echo "Error: LUKS_PASS cannot be empty when ENCRYPTED=true"
        exit 1
    fi
    echo "Setup validation passed."
}

# Cleanup on exit
cleanup() {
    echo "Cleaning up on exit..."
    umount -R /mnt 2>/dev/null || true
    if [ "$ENCRYPTED" = true ]; then
        vgchange -an vg0 2>/dev/null || true
        cryptsetup close archy 2>/dev/null || true
    fi
}
trap cleanup EXIT

validate_setup

echo "Starting Arch Linux installation..."
echo "Encryption: $ENCRYPTED"
echo "Root device: $ROOT_DEV"
echo "EFI boot device: $BOOT_DEV"

# Prepare ESP (always required for UEFI) — WARNING: will destroy data on BOOT_DEV
echo "Formatting EFI System Partition (FAT32)..."
run_command mkfs.fat -F32 "$BOOT_DEV"

if [ "$ENCRYPTED" = true ]; then
    echo "Setting up LUKS + LVM..."
    # LUKS format and open
    echo -n "$LUKS_PASS" | cryptsetup luksFormat "$ROOT_DEV" \
        --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --key-file=-
    echo -n "$LUKS_PASS" | cryptsetup open "$ROOT_DEV" archy --key-file=-

    # LVM on encrypted device
    run_command pvcreate /dev/mapper/archy
    run_command vgcreate vg0 /dev/mapper/archy
    run_command lvcreate --name root --extents 100%FREE vg0

    # Format and mount root
    run_command mkfs.ext4 /dev/vg0/root
    run_command mount /dev/vg0/root /mnt

    ROOT_MOUNT="/dev/vg0/root"
else
    echo "Setting up unencrypted installation..."
    run_command mkfs.ext4 "$ROOT_DEV"
    run_command mount "$ROOT_DEV" /mnt
    ROOT_MOUNT="$ROOT_DEV"
fi

# Mount ESP to /mnt/boot (common for both paths)
run_command mkdir -p /mnt/boot
run_command mount "$BOOT_DEV" /mnt/boot

# Create boot loader entries directory
run_command mkdir -p /mnt/boot/loader/entries

# Base system installation
echo "Installing base system (pacstrap)..."
run_command pacstrap -K /mnt base base-devel \
    linux-hardened linux-hardened-headers \
    linux-zen linux-zen-headers \
    linux-lts linux-lts-headers \
    linux-firmware nano sudo networkmanager git plymouth

# Add LVM2 only when encrypted
if [ "$ENCRYPTED" = true ]; then
    run_command pacstrap -K /mnt lvm2
fi

# Generate fstab (overwrite, never append)
run_command genfstab -U /mnt > /mnt/etc/fstab

# --- Chroot setup ---
# Timezone & clock
run_command arch-chroot /mnt ln -sf /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime
run_command arch-chroot /mnt hwclock --systohc

# Locale
run_command arch-chroot /mnt bash -c "echo 'en_US.UTF-8 UTF-8' >> /etc/locale.gen"
run_command arch-chroot /mnt bash -c "echo 'ar_SA.UTF-8 UTF-8' >> /etc/locale.gen"
run_command arch-chroot /mnt locale-gen
run_command arch-chroot /mnt bash -c "echo 'LANG=en_US.UTF-8' > /etc/locale.conf"
run_command arch-chroot /mnt bash -c "echo 'KEYMAP=us' > /etc/vconsole.conf"

# Hostname & hosts
run_command arch-chroot /mnt bash -c "echo '$HOSTNAME' > /etc/hostname"
run_command arch-chroot /mnt bash -c "cat <<EOL > /etc/hosts
127.0.0.1    localhost
::1          localhost
127.0.1.1    $HOSTNAME.localdomain 
EOL"

# Root and user passwords
run_command arch-chroot /mnt bash -c "echo 'root:$ROOT_PASS' | chpasswd"
run_command arch-chroot /mnt useradd -m -s /bin/bash "$USER"
run_command arch-chroot /mnt bash -c "echo '$USER:$USER_PASS' | chpasswd"

# Create essential groups and add user
for group in wheel audit libvirt firejail network; do
    run_command arch-chroot /mnt groupadd -rf "$group"
    run_command arch-chroot /mnt gpasswd -a "$USER" "$group"
done
run_command arch-chroot /mnt groupadd -rf allow-internet

# --- Partition UUIDs ---
if [ "$ENCRYPTED" = true ]; then
    # For LUKS we need the LUKS container UUID (identifies the partition)
    ROOT_UUID=$(blkid -s UUID -o value "$ROOT_DEV")
else
    # For unencrypted we need the filesystem UUID of the freshly formatted root
    ROOT_UUID=$(blkid -s UUID -o value "$ROOT_DEV")
fi

# --- mkinitcpio and boot entries ---
if [ "$ENCRYPTED" = true ]; then
    # Crypttab for systemd
    run_command arch-chroot /mnt bash -c "echo 'archy UUID=$ROOT_UUID none luks,discard' > /etc/crypttab.initramfs"
    run_command arch-chroot /mnt sed -i 's/^HOOKS.*/HOOKS=(base systemd plymouth autodetect modconf block sd-encrypt lvm2 filesystems keyboard fsck)/' /etc/mkinitcpio.conf

    # Boot entries for each kernel
    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch.conf
title   $HOSTNAME - Linux Hardened (Secure)
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened.img
options rd.luks.name=$ROOT_UUID=archy root=$ROOT_MOUNT rw $HARDENED_PARAMS
EOL"

    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch-zen.conf
title   $HOSTNAME - Linux Zen (Performance)
linux   /vmlinuz-linux-zen
initrd  /initramfs-linux-zen.img
options rd.luks.name=$ROOT_UUID=archy root=$ROOT_MOUNT rw $STANDARD_PARAMS
EOL"

    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch-lts.conf
title   $HOSTNAME - Linux LTS (Stability)
linux   /vmlinuz-linux-lts
initrd  /initramfs-linux-lts.img
options rd.luks.name=$ROOT_UUID=archy root=$ROOT_MOUNT rw $STANDARD_PARAMS
EOL"

    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch-fallback.conf
title   $HOSTNAME System (Encrypted Fallback)
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened-fallback.img
options rd.luks.name=$ROOT_UUID=archy root=$ROOT_MOUNT rw
EOL"
else
    # Unencrypted – no encryption hooks
    run_command arch-chroot /mnt sed -i 's/^HOOKS.*/HOOKS=(base systemd plymouth autodetect modconf block filesystems keyboard fsck)/' /etc/mkinitcpio.conf

    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch.conf
title   $HOSTNAME - Linux Hardened (Secure)
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened.img
options root=UUID=$ROOT_UUID rw $HARDENED_PARAMS
EOL"

    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch-zen.conf
title   $HOSTNAME - Linux Zen (Performance)
linux   /vmlinuz-linux-zen
initrd  /initramfs-linux-zen.img
options root=UUID=$ROOT_UUID rw $STANDARD_PARAMS
EOL"

    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch-lts.conf
title   $HOSTNAME - Linux LTS (Stability)
linux   /vmlinuz-linux-lts
initrd  /initramfs-linux-lts.img
options root=UUID=$ROOT_UUID rw $STANDARD_PARAMS
EOL"

    run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch-fallback.conf
title   $HOSTNAME System (Fallback)
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened-fallback.img
options root=UUID=$ROOT_UUID rw
EOL"
fi

# Bootloader configuration
run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/loader.conf
default  arch.conf
timeout  5
console-mode max
editor   no
EOL"

# --- Package installation from file ---
if [ -n "${PACKAGE_FILE:-}" ] && [ -f "$PACKAGE_FILE" ]; then
    source "$PACKAGE_FILE"
    if [[ -n "${PACKAGES[@]:-}" ]]; then
        for package in "${PACKAGES[@]}"; do
            run_command arch-chroot /mnt pacman --noconfirm --needed -S "$package"
        done
    else
        echo "Warning: PACKAGES array is empty or undefined in $PACKAGE_FILE"
    fi
fi

# Enable NetworkManager
run_command arch-chroot /mnt systemctl enable NetworkManager

# --- Temporary sudo for AUR helper (yay) ---
echo "$USER ALL=(ALL) NOPASSWD:ALL   # temp-for-yay" >> /mnt/etc/sudoers

# Deploy rootfs_clean overlay
if [ -d "rootfs_clean" ]; then
    echo "Deploying rootfs_clean overlay..."
    run_command cp -a rootfs_clean/* /mnt/
    run_command chmod +x /mnt/usr/local/bin/* 2>/dev/null || true
    USER_UID=$(arch-chroot /mnt id -u "$USER")
    run_command sed -i "s/USER_ID = 1000/USER_ID = $USER_UID/" /mnt/usr/local/bin/audit_notify.py 2>/dev/null || true
else
    echo "Warning: rootfs_clean directory not found, skipping overlay."
fi

# Firejail setup
run_command arch-chroot /mnt /usr/bin/firecfg
run_command sed -i "s/USER_PLACEHOLDER/$USER/" /mnt/etc/firejail/firejail.users

# Kernel cmdline file (used by kernel-install scripts)
run_command arch-chroot /mnt mkdir -p /etc/kernel
if [ "$ENCRYPTED" = true ]; then
    echo "rd.luks.name=$ROOT_UUID=archy root=$ROOT_MOUNT rw $HARDENED_PARAMS" > /mnt/etc/kernel/cmdline
else
    echo "root=UUID=$ROOT_UUID rw $HARDENED_PARAMS" > /mnt/etc/kernel/cmdline
fi

# Install systemd-boot
run_command arch-chroot /mnt bootctl install

# Plymouth theme
run_command arch-chroot /mnt plymouth-set-default-theme -R arch-charge

# --- AUR helper (yay-bin) installation ---
run_command arch-chroot /mnt su - "$USER" -c "git clone https://aur.archlinux.org/yay-bin.git /home/$USER/yay-bin"
run_command arch-chroot /mnt su - "$USER" -c "cd /home/$USER/yay-bin && makepkg -si --noconfirm"
run_command arch-chroot /mnt rm -rf "/home/$USER/yay-bin"

# Install AUR packages if defined
if [[ -n "${AUR[@]:-}" ]]; then
    for aurpkg in "${AUR[@]}"; do
        echo "Installing AUR package: $aurpkg"
        run_command arch-chroot /mnt su - "$USER" -c "yay --noconfirm -S '$aurpkg'"
    done
else
    echo "No AUR packages to install."
fi

# Remove temporary sudo privilege (only our tagged line)
run_command sed -i '/# temp-for-yay$/d' /mnt/etc/sudoers

# Regenerate initramfs for all kernels
run_command arch-chroot /mnt mkinitcpio -P

# --- Final verification ---
echo "Verifying installation..."
if [ "$ENCRYPTED" = true ]; then
    blkid "$ROOT_DEV" | grep -q "crypto_LUKS" && echo "✓ LUKS encryption verified" || echo "Warning: LUKS check failed"
fi

if [ -f "/mnt/boot/loader/entries/arch.conf" ] && \
   [ -f "/mnt/boot/loader/entries/arch-zen.conf" ] && \
   [ -f "/mnt/boot/loader/entries/arch-lts.conf" ]; then
    echo "✓ All kernel loader entries present"
else
    echo "Warning: One or more boot entries missing!"
fi

echo "Installation complete! Log saved to: $LOG_FILE"

# Copy Hyprland installer for post-reboot
if [ -f "install-hyprland-dots.sh" ]; then
    run_command cp install-hyprland-dots.sh /mnt/home/$USER/
    run_command chown "$(arch-chroot /mnt id -u $USER):$(arch-chroot /mnt id -g $USER)" /mnt/home/$USER/install-hyprland-dots.sh
    run_command chmod +x /mnt/home/$USER/install-hyprland-dots.sh
    echo -e "\n==========================================\n  POST-REBOOT SETUP\n=========================================="
    echo "After rebooting, log in as '$USER' and run:"
    echo "  cd ~"
    echo "  ./install-hyprland-dots.sh"
    echo "This will install end-4's Hyprland dotfiles."
fi

echo -e "\nYou can reboot now with: reboot"