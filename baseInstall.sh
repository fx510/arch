#!/bin/bash

## VAR 

ROOT_DEV="/dev/nvme0n1p99"
BOOT_DEV="/dev/nvme0n1p98"
USER="USER"
USER_PASS="${USER_PASS:-}"      # Set via env before running
ROOT_PASS="${ROOT_PASS:-}"      # Set via env before running
LUKS_PASS="asdasdasd"   # Set via env before running
HOSTNAME="archyBTW"	#Hostname

# MKMODULES="i915"
PACKAGE_FILE="packages.cfg"


run_command() {
    "$@"  
    # Check if the command failed
    if [ $? -ne 0 ]; then
        # Print the error message in 
        echo -e "\033[0;31mError: Command failed : $@  \033[0m"

    fi
}

# 
#umount -R /mnt  && vgchange -an vg0  && cryptsetup close /dev/mapper/archy 

## this will remove all disk parts nd create 2 part 
## I prefer to do that manually 
# sgdisk --zap-all /dev/vda
# sgdisk -n 1:0:+512M -t 1:ef00 /dev/vda  # EFI partition
# sgdisk -n 2:0:0 -t 2:8309 /dev/vda      # LUKS partition


# Set up LUKS on the root partition
echo -n "$LUKS_PASS" | cryptsetup luksFormat "$ROOT_DEV"   --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --use-random -

# Open LUKS partition
echo -n "$LUKS_PASS" | cryptsetup open "$ROOT_DEV" archy -

## Create LVM 
run_command pvcreate /dev/mapper/archy
run_command vgcreate vg0 /dev/mapper/archy
run_command lvcreate --name root --extents 100%FREE vg0


run_command mkfs.ext4 /dev/vg0/root
run_command mount /dev/vg0/root /mnt
run_command mkdir /mnt/boot 
echo "mounting boot $BOOT_DEV " 
sleep 2
run_command mount $BOOT_DEV /mnt/boot
run_command arch-chroot /mnt mkdir -p /boot/loader/entries/

run_command pacstrap -K /mnt  base base-devel linux-hardened linux-firmware nano  wget sudo networkmanager git lvm2  plymouth

run_command genfstab -U /mnt >> /mnt/etc/fstab

 
run_command arch-chroot /mnt ln -s /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime

run_command arch-chroot /mnt hwclock --systohc

run_command arch-chroot /mnt bash -c "echo 'en_US.UTF-8 UTF-8' >> /etc/locale.gen"
run_command arch-chroot /mnt bash -c "echo 'ar_SA.UTF-8 UTF-8' >> /etc/locale.gen"

run_command arch-chroot /mnt locale-gen
run_command arch-chroot /mnt echo LANG=en_US.UTF-8 > /etc/locale.conf

run_command arch-chroot /mnt bash -c "echo 'KEYMAP=us' > /etc/vconsole.conf"

run_command arch-chroot /mnt bash -c "echo $HOSTNAME > /etc/hostname"

# Configure /etc/hosts file
run_command arch-chroot /mnt bash -c "cat <<EOL > /etc/hosts
127.0.0.1    localhost
::1          localhost
127.0.1.1    $HOSTNAME.localdomain 
EOL"

run_command arch-chroot /mnt bash -c "echo 'root:$ROOT_PASS' | chpasswd"

run_command arch-chroot /mnt useradd -m -s /bin/sh $USER
run_command arch-chroot /mnt bash -c "echo '$USER:$USER_PASS' | chpasswd"

# Add user to groups
for group in wheel audit libvirt firejail; do
    run_command arch-chroot /mnt groupadd -rf "$group"
    run_command arch-chroot /mnt gpasswd -a "$USER" "$group"
done

run_command arch-chroot /mnt groupadd -rf allow-internet

## edit mkinitcpio.conf to lvm2 and systemd boot 
run_command arch-chroot /mnt sed -i 's/^HOOKS.*/HOOKS=(base systemd plymouth autodetect modconf block sd-encrypt lvm2 filesystems keyboard fsck)/' /etc/mkinitcpio.conf

## Add entrie for systemd
run_command arch-chroot /mnt bash -c "cat <<EOL > /boot/loader/entries/arch.conf
title   Arch Linux Hardened
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened.img
options rd.luks.name=$(blkid -s UUID -o value "$ROOT_DEV")=archy root=/dev/vg0/root rw quiet splash rd.luks.options=discard,timeout=10
EOL"



source "$PACKAGE_FILE"
# Check if PACKAGE_FILE is defined and exists
if [ -z "$PACKAGE_FILE" ]; then
    echo "Error: PACKAGE_FILE variable is not set."
  
fi

if [ ! -f "$PACKAGE_FILE" ]; then
    echo "Error: PACKAGE_FILE '$PACKAGE_FILE' does not exist."
  
fi

# Source the package configuration file


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

run_command arch-chroot /mnt systemctl enable NetworkManager

# Temporarily allow sudo without password for yay setup
run_command arch-chroot /mnt bash -c "echo '$USER ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers"



# add copu rootfs into /mnt


# Setup firejail
arch-chroot /mnt /usr/bin/firecfg
echo "$user" >/mnt/etc/firejail/firejail.users

{
  echo -n "lsm=landlock,lockdown,yama,integrity,apparmor,bpf "
  echo -n "lockdown=integrity "
  echo -n "mem_sleep_default=deep "
  echo -n "audit=1 audit_backlog_limit=32768 "
  echo -n "quiet splash rd.udev.log_level=3"
} > /mnt/etc/kernel/cmdline


## install Systemd Bootloader 
arch-chroot /mnt bootctl install


arch-chroot /mnt plymouth-set-default-theme -R arch-charge


# Remove sudo NOPASSWD rights from user
sed -i '$ d' /mnt/etc/sudoers


# sed -i "s/username_placeholder/$user/g" /mnt/etc/libvirt/qemu.conf
# mv rootfs/home/user rootfs/home/$USER
## add move rootfs config 


## intall YAY
arch-chroot -u $USER /mnt /bin/bash -c 'mkdir /tmp/yay.$$ && \
                                          cd /tmp/yay.$$ && \
                                          curl "https://aur.archlinux.org/cgit/aur.git/plain/PKGBUILD?h=yay-bin" -o PKGBUILD && \
                                          makepkg -si --noconfirm'

# Install each AUR package in the AUR array Packages.cfg
for aurpkg in "${AUR[@]}"; do
        run_command arch-chroot /mnt su - $USER -c "yay --noconfirm -Sy"

        echo "Installing $aurpkg ..."
        if ! run_command arch-chroot /mnt su - $USER -c "yay --noconfirm -Sy $aurpkg" ; then
            echo "Failed to install $aurpkg. Continuing with the next package..."
        else
            echo "Successfully installed $aurpkg."
        fi
done
 
## Just in case  :D
arch-chroot /mnt mkinitcpio -P
umount -R /mnt && vgchange -an vg0 && cryptsetup close /dev/mapper/archy 

## TODO :
# add check blkid $ROOT_DEV and arch.conf before reboot 
# add hyprland ml4w
# yay -S ml4w-hyprland-git

echo "Installation complete. Reboot your system."


