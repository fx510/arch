#!/usr/bin/env python3
"""
Arch Linux installation script
Run as root.
"""

import subprocess
import sys
import os
import shutil
import re
import time
from pathlib import Path
from datetime import datetime
import atexit

# ========== CONFIGURATION ==========
ROOT_DEV = "/dev/nvme0n1p2"
BOOT_DEV = "/dev/nvme0n1p1"
USER = "test"
USER_PASS = "asdasd"
ROOT_PASS = "test"
LUKS_PASS = "asdasd"
HOSTNAME = "archyBTW"
ENCRYPTED = True

PACKAGE_FILE = "packages.cfg"

HARDENED_PARAMS = "lsm=landlock,lockdown,yama,integrity,apparmor,bpf lockdown=integrity mem_sleep_default=deep audit=1 audit_backlog_limit=32768 quiet splash rd.udev.log_level=3"
STANDARD_PARAMS = "quiet splash rd.udev.log_level=3"

LOG_FILE = f"/tmp/arch_install_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Retry settings for pacstrap
PACSTRAP_RETRIES = 3
PACSTRAP_RETRY_DELAY = 10  # seconds

# ========== HELPER FUNCTIONS ==========
def log_print(msg: str, is_error: bool = False):
    if is_error:
        msg = f"\033[31m{msg}\033[0m"
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def run_command(cmd, **kwargs):
    """Run a command, real‑time output, exit on failure."""
    log_print(f"$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    try:
        if isinstance(cmd, str):
            subprocess.run(cmd, shell=True, check=True, **kwargs)
        else:
            subprocess.run(cmd, check=True, **kwargs)
    except subprocess.CalledProcessError as e:
        log_print(f"Error: Command failed with exit code {e.returncode}: {cmd}", is_error=True)
        sys.exit(1)

def run_command_with_retry(cmd, description, max_retries=3, delay=10):
    """Run a command, retry on failure up to max_retries times."""
    for attempt in range(1, max_retries + 1):
        log_print(f"Attempt {attempt}/{max_retries}: {description}")
        try:
            run_command(cmd)
            return True
        except SystemExit:
            if attempt == max_retries:
                raise
            log_print(f"Command failed, retrying in {delay} seconds...", is_error=True)
            time.sleep(delay)
    return False

def run_chroot(cmd, input_text=None):
    """Run a command inside /mnt using arch-chroot.
       If cmd is a string, it is passed to bash -c (preserves quotes, pipes, redirections).
       If cmd is a list, it is executed directly.
    """
    if isinstance(cmd, str):
        full_cmd = ["arch-chroot", "/mnt", "bash", "-c", cmd]
    else:
        full_cmd = ["arch-chroot", "/mnt"] + cmd
    run_command(full_cmd, input=input_text)

def write_file(path: Path, content: str, chroot: bool = False):
    if chroot:
        dest = Path("/mnt") / path
    else:
        dest = path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    log_print(f"Wrote {dest}")

def parse_package_file(filepath: str):
    packages, aur = [], []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    pkg_match = re.search(r'PACKAGES\s*=\s*\(\s*([^)]+)\s*\)', content, re.DOTALL)
    if pkg_match:
        packages = [p for p in pkg_match.group(1).split() if p and not p.startswith('#')]
    aur_match = re.search(r'AUR\s*=\s*\(\s*([^)]+)\s*\)', content, re.DOTALL)
    if aur_match:
        aur = [a for a in aur_match.group(1).split() if a and not a.startswith('#')]
    return packages, aur

def cleanup():
    log_print("Cleaning up on exit...")
    subprocess.run("umount -R /mnt 2>/dev/null", shell=True, check=False)
    if ENCRYPTED:
        subprocess.run("vgchange -an vg0 2>/dev/null", shell=True, check=False)
        subprocess.run("cryptsetup close archy 2>/dev/null", shell=True, check=False)

atexit.register(cleanup)

# ========== VALIDATION ==========
def validate_setup():
    log_print("Validating setup...")
    if not Path(ROOT_DEV).exists():
        log_print(f"Root device {ROOT_DEV} not found", is_error=True); sys.exit(1)
    if not Path(BOOT_DEV).exists():
        log_print(f"EFI boot device {BOOT_DEV} not found", is_error=True); sys.exit(1)
    if not Path(PACKAGE_FILE).exists():
        log_print(f"Package file {PACKAGE_FILE} not found", is_error=True); sys.exit(1)
    if not Path("/sys/firmware/efi").exists():
        log_print("System not booted in UEFI mode", is_error=True); sys.exit(1)
    if ENCRYPTED and not LUKS_PASS:
        log_print("LUKS_PASS cannot be empty when ENCRYPTED=true", is_error=True); sys.exit(1)
    log_print("Setup validation passed.")

def setup_reflector():
    log_print("Installing reflector on live system...")
    run_command("pacman -Sy --noconfirm reflector")
    
    log_print("Generating optimized mirrorlist (Spain/France, HTTPS, latest 30, by rate)...")
    # Improved reflector command: country-specific, no --fastest (uses rate sorting), more threads
    run_command("reflector   --latest 30 --protocol https --sort rate --threads 10 --save /etc/pacman.d/mirrorlist")
    
    # Verify mirrorlist
    result = subprocess.run("grep -E '^Server' /etc/pacman.d/mirrorlist | head -5", shell=True, capture_output=True, text=True)
    if result.stdout.strip():
        log_print(f"✓ Mirrorlist generated with {len(result.stdout.strip().splitlines())} entries (first 5 shown):\n{result.stdout}")
    else:
        log_print("⚠️ Mirrorlist appears empty, falling back to generic reflector command", is_error=True)
        run_command("reflector --latest 30 --protocol https --sort rate --save /etc/pacman.d/mirrorlist")
    
    # Update pacman database to use new mirrors
    run_command("pacman -Syy")

# ========== DISK SETUP ==========
def setup_disks():
    """Format and mount disk partitions."""
    log_print("=" * 60)
    log_print("DISK SETUP")
    log_print("=" * 60)
    
    # Format ESP
    log_print("Formatting EFI System Partition (FAT32)...")
    run_command(f"mkfs.fat -F32 {BOOT_DEV}")

    if ENCRYPTED:
        log_print("Setting up LUKS + LVM...")
        # LUKS format
        proc = subprocess.run(
            f"echo -n '{LUKS_PASS}' | cryptsetup luksFormat {ROOT_DEV} --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --key-file=-",
            shell=True, capture_output=True, text=True
        )
        if proc.returncode != 0:
            log_print(f"LUKS format failed: {proc.stderr}", is_error=True); sys.exit(1)
        # Open LUKS
        proc = subprocess.run(
            f"echo -n '{LUKS_PASS}' | cryptsetup open {ROOT_DEV} archy --key-file=-",
            shell=True, capture_output=True, text=True
        )
        if proc.returncode != 0:
            log_print(f"LUKS open failed: {proc.stderr}", is_error=True); sys.exit(1)

        run_command("pvcreate /dev/mapper/archy")
        run_command("vgcreate vg0 /dev/mapper/archy")
        run_command("lvcreate --name root --extents 100%FREE vg0")
        run_command("mkfs.ext4 /dev/vg0/root")
        run_command("mount /dev/vg0/root /mnt")
        root_mount = "/dev/vg0/root"
    else:
        log_print("Setting up unencrypted installation...")
        run_command(f"mkfs.ext4 {ROOT_DEV}")
        run_command(f"mount {ROOT_DEV} /mnt")
        root_mount = ROOT_DEV

    # Mount ESP
    Path("/mnt/boot").mkdir(parents=True, exist_ok=True)
    run_command(f"mount {BOOT_DEV} /mnt/boot")
    Path("/mnt/boot/loader/entries").mkdir(parents=True, exist_ok=True)
    
    log_print("✓ Disk setup complete")
    return root_mount

# ========== BASE SYSTEM INSTALLATION ==========
def install_base_system():
    """Install base Arch Linux system with kernels and essential packages."""
    log_print("=" * 60)
    log_print("BASE SYSTEM INSTALLATION")
    log_print("=" * 60)
    
    # base_pkgs = "base base-devel linux-hardened linux-hardened-headers linux-zen linux-zen-headers linux-lts linux-lts-headers linux-firmware nano sudo networkmanager git plymouth"
    base_pkgs = "base base-devel linux-hardened  linux-firmware nano sudo networkmanager git plymouth"
    
    log_print(f"Installing base system: {base_pkgs}")
    log_print("Note: This may take a while. Retry logic is active (max 3 attempts).")
    
    # Retry loop for pacstrap
    for attempt in range(1, PACSTRAP_RETRIES + 1):
        log_print(f"\n--- pacstrap attempt {attempt}/{PACSTRAP_RETRIES} ---")
        try:
            # Use run_command directly so failure raises exception
            if isinstance(base_pkgs, str):
                cmd = f"pacstrap -K /mnt {base_pkgs}"
            else:
                cmd = ["pacstrap", "-K", "/mnt"] + base_pkgs
            run_command(cmd)
            log_print("✓ Base system installation successful")
            break
        except SystemExit:
            if attempt == PACSTRAP_RETRIES:
                log_print("FATAL: pacstrap failed after all retries", is_error=True)
                raise
            log_print(f"pacstrap failed (attempt {attempt}). Regenerating mirrorlist and retrying in {PACSTRAP_RETRY_DELAY} seconds...", is_error=True)
            # Refresh mirrors and pacman cache before retry
            run_command("reflector --latest 30 --protocol https --sort rate --save /etc/pacman.d/mirrorlist")
            run_command("pacman -Syy")
            time.sleep(PACSTRAP_RETRY_DELAY)
    
    if ENCRYPTED:
        log_print("Installing LVM2 for encrypted setup...")
        run_command("pacstrap -K /mnt lvm2")
    
    log_print("✓ Base system installation complete")

# ========== SYSTEM CONFIGURATION ==========
def configure_system(root_mount):
    """Configure the installed system (locale, timezone, users, etc.)."""
    log_print("=" * 60)
    log_print("SYSTEM CONFIGURATION")
    log_print("=" * 60)
    
    # Generate fstab
    run_command("genfstab -U /mnt > /mnt/etc/fstab")
    
    # Chroot configuration
    log_print("Configuring system inside chroot...")
    run_chroot("ln -sf /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime")
    run_chroot("hwclock --systohc")
    run_chroot("bash -c \"echo 'en_US.UTF-8 UTF-8' >> /etc/locale.gen\"")
    run_chroot("bash -c \"echo 'ar_SA.UTF-8 UTF-8' >> /etc/locale.gen\"")
    run_chroot("locale-gen")
    write_file(Path("/etc/locale.conf"), "LANG=en_US.UTF-8", chroot=True)
    write_file(Path("/etc/vconsole.conf"), "KEYMAP=us", chroot=True)
    write_file(Path("/etc/hostname"), f"{HOSTNAME}\n", chroot=True)
    hosts = f"127.0.0.1\tlocalhost\n::1\t\tlocalhost\n127.0.1.1\t{HOSTNAME}.localdomain\n"
    write_file(Path("/etc/hosts"), hosts, chroot=True)
    
    # Set passwords
    run_chroot(f"echo 'root:{ROOT_PASS}' | chpasswd")
    run_chroot(f"useradd -m -s /bin/bash {USER}")
    run_chroot(f"echo '{USER}:{USER_PASS}' | chpasswd")
    
    # Add user to groups
    for group in ["wheel", "audit", "libvirt", "firejail", "network"]:
        run_chroot(f"groupadd -rf {group}")
        run_chroot(f"gpasswd -a {USER} {group}")
    run_chroot("groupadd -rf allow-internet")
    
    log_print("✓ System configuration complete")

# ========== BOOT CONFIGURATION ==========
def configure_boot(root_mount):
    """Configure bootloader and kernel boot entries."""
    log_print("=" * 60)
    log_print("BOOT CONFIGURATION")
    log_print("=" * 60)
    
    # Get UUIDs
    if ENCRYPTED:
        root_uuid = subprocess.run(f"blkid -s UUID -o value {ROOT_DEV}", capture_output=True, text=True, shell=True).stdout.strip()
    else:
        root_uuid = subprocess.run(f"blkid -s UUID -o value {ROOT_DEV}", capture_output=True, text=True, shell=True).stdout.strip()

    # mkinitcpio hooks and boot entries
    if ENCRYPTED:
        write_file(Path("/etc/crypttab.initramfs"), f"archy UUID={root_uuid} none luks,discard\n", chroot=True)
        run_chroot("sed -i 's/^HOOKS.*/HOOKS=(base systemd plymouth autodetect modconf block sd-encrypt lvm2 filesystems keyboard fsck)/' /etc/mkinitcpio.conf")
        
        # Hardened kernel boot entry
        boot_conf = f"""title   {HOSTNAME} - Linux Hardened (Secure)
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened.img
options rd.luks.name={root_uuid}=archy root={root_mount} rw {HARDENED_PARAMS}
"""
        write_file(Path("/boot/loader/entries/arch.conf"), boot_conf, chroot=True)
        
        # Zen kernel boot entry
        zen_conf = boot_conf.replace("linux-hardened", "linux-zen").replace("initramfs-linux-hardened", "initramfs-linux-zen").replace(HARDENED_PARAMS, STANDARD_PARAMS)
        write_file(Path("/boot/loader/entries/arch-zen.conf"), zen_conf, chroot=True)
        
        # LTS kernel boot entry
        lts_conf = boot_conf.replace("linux-hardened", "linux-lts").replace("initramfs-linux-hardened", "initramfs-linux-lts").replace(HARDENED_PARAMS, STANDARD_PARAMS)
        write_file(Path("/boot/loader/entries/arch-lts.conf"), lts_conf, chroot=True)
        
        # Fallback boot entry
        fallback_conf = boot_conf.replace("initramfs-linux-hardened.img", "initramfs-linux-hardened-fallback.img").replace(HARDENED_PARAMS, "")
        write_file(Path("/boot/loader/entries/arch-fallback.conf"), fallback_conf, chroot=True)
    else:
        run_chroot("sed -i 's/^HOOKS.*/HOOKS=(base systemd plymouth autodetect modconf block filesystems keyboard fsck)/' /etc/mkinitcpio.conf")
        
        # Hardened kernel boot entry
        boot_conf = f"""title   {HOSTNAME} - Linux Hardened (Secure)
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened.img
options root=UUID={root_uuid} rw {HARDENED_PARAMS}
"""
        write_file(Path("/boot/loader/entries/arch.conf"), boot_conf, chroot=True)
        
        # Zen kernel boot entry
        zen_conf = f"""title   {HOSTNAME} - Linux Zen
linux   /vmlinuz-linux-zen
initrd  /initramfs-linux-zen.img
options root=UUID={root_uuid} rw {STANDARD_PARAMS}
"""
        write_file(Path("/boot/loader/entries/arch-zen.conf"), zen_conf, chroot=True)
        
        # LTS kernel boot entry
        lts_conf = f"""title   {HOSTNAME} - Linux LTS
linux   /vmlinuz-linux-lts
initrd  /initramfs-linux-lts.img
options root=UUID={root_uuid} rw {STANDARD_PARAMS}
"""
        write_file(Path("/boot/loader/entries/arch-lts.conf"), lts_conf, chroot=True)
        
        # Fallback boot entry
        fallback_conf = f"""title   {HOSTNAME} - Linux Hardened (Fallback)
linux   /vmlinuz-linux-hardened
initrd  /initramfs-linux-hardened-fallback.img
options root=UUID={root_uuid} rw
"""
        write_file(Path("/boot/loader/entries/arch-fallback.conf"), fallback_conf, chroot=True)

    # Bootloader config
    write_file(Path("/boot/loader/loader.conf"), "default arch.conf\ntimeout 5\nconsole-mode max\neditor no\n", chroot=True)

    # Kernel cmdline
    Path("/mnt/etc/kernel").mkdir(parents=True, exist_ok=True)
    cmdline = f"rd.luks.name={root_uuid}=archy root={root_mount} rw {HARDENED_PARAMS}" if ENCRYPTED else f"root=UUID={root_uuid} rw {HARDENED_PARAMS}"
    write_file(Path("/etc/kernel/cmdline"), cmdline, chroot=True)

    
    log_print("✓ Boot configuration complete")

# ========== REGULAR PACKAGES INSTALLATION ==========
def install_regular_packages():
    """Install regular packages from packages.cfg."""
    log_print("=" * 60)
    log_print("REGULAR PACKAGES INSTALLATION")
    log_print("=" * 60)
    
    packages, aur_packages = parse_package_file(PACKAGE_FILE)
    
    if packages:
        total = len(packages)
        log_print(f"==> Found {total} regular packages in {PACKAGE_FILE}")
        for idx, pkg in enumerate(packages, 1):
            log_print(f"==> [{idx}/{total}] Installing package: {pkg}")
            run_chroot(f"pacman --noconfirm --needed -S {pkg}")
        log_print(f"✓ Successfully installed {total} regular packages")
    else:
        log_print(f"Warning: No regular packages found in {PACKAGE_FILE}", is_error=True)
    
    return aur_packages  # Return AUR packages for later installation

# ========== AUR PACKAGES INSTALLATION ==========
def install_aur_packages(aur_packages):
    """Install AUR packages using yay."""
    log_print("=" * 60)
    log_print("AUR PACKAGES INSTALLATION")
    log_print("=" * 60)
    
    # Install reflector in target system
    log_print("Installing reflector in target system...")
     
    run_chroot("systemctl enable NetworkManager")
    run_chroot(f"bash -c \"echo '{USER} ALL=(ALL) NOPASSWD:ALL   # temp-for-yay' >> /etc/sudoers\"")

    # AUR helper
    log_print("Installing yay-bin (AUR helper)...")
    run_chroot(f"su - {USER} -c 'git clone https://aur.archlinux.org/yay-bin.git /home/{USER}/yay-bin'")
    run_chroot(f"su - {USER} -c 'cd /home/{USER}/yay-bin && makepkg -si --noconfirm'")
    run_chroot(f"rm -rf /home/{USER}/yay-bin")

    if aur_packages:
        total_aur = len(aur_packages)
        log_print(f"==> Installing {total_aur} AUR packages")
        for idx, aurpkg in enumerate(aur_packages, 1):
            log_print(f"==> [{idx}/{total_aur}] Installing AUR package: {aurpkg}")
            # Note: yay may ask for confirmation even with --noconfirm, but it's usually fine
            run_chroot(f"su - {USER} -c 'yay --noconfirm -S {aurpkg}'")
        log_print(f"✓ Successfully installed {total_aur} AUR packages")
    else:
        log_print("No AUR packages to install")

    run_chroot("sed -i '/# temp-for-yay$/d' /etc/sudoers")

# ========== POST-INSTALLATION ==========
def post_installation():
    """Post-installation tasks (rootfs overlay, firejail, etc.)."""
    # we need to install plymouth-set-default-theme in the end 
    run_chroot("bootctl install")
    run_chroot("plymouth-set-default-theme -R arch-charge")

    log_print("=" * 60)
    log_print("POST-INSTALLATION TASKS")
    log_print("=" * 60)
    
    # Deploy rootfs_clean overlay if present
    if Path("rootfs_clean").is_dir():
        log_print("Deploying rootfs_clean overlay...")
        run_command("cp -a rootfs_clean/* /mnt/")
        for f in Path("/mnt/usr/local/bin").glob("*"):
            if f.is_file(): f.chmod(0o755)
        uid = subprocess.run(f"arch-chroot /mnt id -u {USER}", capture_output=True, text=True, shell=True).stdout.strip()
        audit_script = Path("/mnt/usr/local/bin/audit_notify.py")
        if audit_script.exists():
            audit_script.write_text(audit_script.read_text().replace("USER_ID = 1000", f"USER_ID = {uid}"))

    run_chroot("/usr/bin/firecfg")
    firejail_users = Path("/mnt/etc/firejail/firejail.users")
    if firejail_users.exists():
        firejail_users.write_text(firejail_users.read_text().replace("USER_PLACEHOLDER", USER))
    
    run_chroot("mkinitcpio -P")
    
    log_print("✓ Post-installation tasks complete")

# ========== VERIFICATION ==========
def verify_installation():
    """Verify the installation was successful."""
    log_print("=" * 60)
    log_print("INSTALLATION VERIFICATION")
    log_print("=" * 60)
    
    if ENCRYPTED:
        chk = subprocess.run(f"blkid {ROOT_DEV} | grep -q 'crypto_LUKS'", shell=True)
        log_print("✓ LUKS encryption verified" if chk.returncode == 0 else "Warning: LUKS check failed")
    
    boot_files = ["/mnt/boot/loader/entries/arch.conf", "/mnt/boot/loader/entries/arch-zen.conf", "/mnt/boot/loader/entries/arch-lts.conf"]
    all_present = all(Path(f).exists() for f in boot_files)
    log_print("✓ All kernel loader entries present" if all_present else "Warning: One or more boot entries missing!")
    
    # Check if key packages are installed (optional)
    try:
        result = run_chroot("pacman -Q linux-hardened")
        log_print("✓ linux-hardened kernel installed")
    except:
        log_print("⚠️ linux-hardened kernel not found", is_error=True)
    
    log_print("✓ Installation verification complete")

# ========== FINAL SETUP ==========
def final_setup():
    """Copy Hyprland installer and show post-reboot instructions."""
    log_print("=" * 60)
    log_print("FINAL SETUP")
    log_print("=" * 60)
    
    # Copy Hyprland installer (if exists)
    hypr = Path("install-hyprland-dots.sh")
    if hypr.exists():
        dest = Path(f"/mnt/home/{USER}/install-hyprland-dots.sh")
        shutil.copy(hypr, dest)
        uid = subprocess.run(f"arch-chroot /mnt id -u {USER}", capture_output=True, text=True, shell=True).stdout.strip()
        gid = subprocess.run(f"arch-chroot /mnt id -g {USER}", capture_output=True, text=True, shell=True).stdout.strip()
        if uid and gid:
            os.chown(dest, int(uid), int(gid))
        dest.chmod(0o755)
        log_print("\n==========================================\n  POST-REBOOT SETUP\n==========================================")
        log_print(f"After rebooting, log in as '{USER}' and run: cd ~ && ./install-hyprland-dots.sh")
        log_print("This will install end-4's Hyprland dotfiles.")
    else:
        log_print("No Hyprland installer found, skipping.")

    log_print(f"\nInstallation complete! Log saved to: {LOG_FILE}")
    log_print("\nYou can reboot now with: reboot")

# ========== MAIN ==========
def main():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Installation log started at {datetime.now()}\n")
    log_print(f"Log file: {LOG_FILE}")

    validate_setup()
    setup_reflector()

    log_print("\n" + "=" * 60)
    log_print("ARCH LINUX INSTALLATION STARTING")
    log_print("=" * 60)
    log_print(f"Encryption: {ENCRYPTED}")
    log_print(f"Root device: {ROOT_DEV}")
    log_print(f"EFI boot device: {BOOT_DEV}")
    log_print("=" * 60 + "\n")

    # Installation steps
    root_mount = setup_disks()
    install_base_system()
    configure_system(root_mount)
    configure_boot(root_mount)
    aur_packages = install_regular_packages()
    install_aur_packages(aur_packages)
    post_installation()
    verify_installation()
    final_setup()

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("This script must be run as root.", file=sys.stderr)
        sys.exit(1)
    main()