#!/usr/bin/env python3
"""
Arch Linux installation script – refined version
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
LUKS_PASS = "asdasd"           # Only used if ENCRYPTED=True
HOSTNAME = "archyBTW"
ENCRYPTED = True

PACKAGE_FILE = "packages.cfg"

# Kernels to install – choose any subset, the script adapts boot entries accordingly
KERNELS = ["linux-hardened"]                # e.g., also add "linux-zen", "linux-lts"
KERNEL_HEADERS = ["linux-hardened-headers"] # keep in sync with kernels

# Kernel command line parameters
HARDENED_PARAMS = (
    "lsm=landlock,lockdown,yama,integrity,apparmor,bpf lockdown=integrity "
    "mem_sleep_default=deep audit=1 audit_backlog_limit=32768 "
    "quiet splash rd.udev.log_level=3"
)
STANDARD_PARAMS = "quiet splash rd.udev.log_level=3"

LOG_FILE = f"/tmp/arch_install_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

PACSTRAP_RETRIES = 3
PACSTRAP_RETRY_DELAY = 10

# ========== HELPER FUNCTIONS ==========
def log_print(msg: str, is_error: bool = False):
    if is_error:
        msg = f"\033[31m{msg}\033[0m"
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def run_command(cmd, check=True, **kwargs):
    """Run a command, log it, optionally exit on failure.
       If cmd is a string, shell=True is used.
       Returns a CompletedProcess if check=False, otherwise raises on failure."""
    log_print(f"$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    try:
        if isinstance(cmd, str):
            return subprocess.run(cmd, shell=True, check=check, **kwargs)
        else:
            return subprocess.run(cmd, check=check, **kwargs)
    except subprocess.CalledProcessError as e:
        if check:
            log_print(f"Error: Command failed with exit code {e.returncode}: {cmd}", is_error=True)
            raise  # re-raise to let caller handle
        else:
            return e

def run_command_retry(cmd, description, max_retries=3, delay=10):
    """Run a command, retrying on failure."""
    for attempt in range(1, max_retries + 1):
        log_print(f"Attempt {attempt}/{max_retries}: {description}")
        try:
            run_command(cmd)
            return True
        except subprocess.CalledProcessError:
            if attempt == max_retries:
                log_print(f"FATAL: {description} failed after {max_retries} attempts", is_error=True)
                sys.exit(1)
            log_print(f"Retrying in {delay} seconds...", is_error=True)
            time.sleep(delay)
    return False

def run_chroot(cmd, input_text=None):
    """Run a command inside /mnt using arch-chroot.
       If cmd is a string, it is passed to bash -c."""
    if isinstance(cmd, str):
        full_cmd = ["arch-chroot", "/mnt", "bash", "-c", cmd]
    else:
        full_cmd = ["arch-chroot", "/mnt"] + cmd
    run_command(full_cmd, input=input_text)

def write_file(path: Path, content: str, chroot: bool = False):
    dest = Path("/mnt") / path if chroot else path
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
        sys.exit(f"Root device {ROOT_DEV} not found")
    if not Path(BOOT_DEV).exists():
        sys.exit(f"EFI boot device {BOOT_DEV} not found")
    if not Path(PACKAGE_FILE).exists():
        sys.exit(f"Package file {PACKAGE_FILE} not found")
    if not Path("/sys/firmware/efi").exists():
        sys.exit("System not booted in UEFI mode")
    if ENCRYPTED and not LUKS_PASS:
        sys.exit("LUKS_PASS cannot be empty when ENCRYPTED=true")
    log_print("Setup validation passed.")

def setup_reflector():
    log_print("Installing reflector on live system and generating mirrorlist...")
    run_command("pacman -Sy --noconfirm reflector")
    run_command(
        "reflector --country Spain --country France --latest 30 --protocol https --sort rate --threads 10 --save /etc/pacman.d/mirrorlist"
    )
    # Verify
    result = subprocess.run("grep -c '^Server' /etc/pacman.d/mirrorlist", shell=True, capture_output=True, text=True)
    servers = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
    log_print(f"✓ Mirrorlist contains {servers} servers.")
    run_command("pacman -Syy")

# ========== DISK SETUP ==========
def setup_disks():
    log_print("=" * 60)
    log_print("DISK SETUP")
    log_print("=" * 60)
    
    # Format ESP
    run_command(f"mkfs.fat -F32 {BOOT_DEV}")

    if ENCRYPTED:
        log_print("Setting up LUKS + LVM...")
        # LUKS format – pipe password directly
        run_command(f"echo -n '{LUKS_PASS}' | cryptsetup luksFormat {ROOT_DEV} --type luks2 --cipher aes-xts-plain64 --key-size 512 --hash sha512 --key-file=-")
        # Open LUKS
        run_command(f"echo -n '{LUKS_PASS}' | cryptsetup open {ROOT_DEV} archy --key-file=-")

        run_command("pvcreate /dev/mapper/archy")
        run_command("vgcreate vg0 /dev/mapper/archy")
        run_command("lvcreate --name root --extents 100%FREE vg0")
        run_command("mkfs.ext4 /dev/vg0/root")
        run_command("mount /dev/vg0/root /mnt")
        root_mount = "/dev/vg0/root"
    else:
        run_command(f"mkfs.ext4 {ROOT_DEV}")
        run_command(f"mount {ROOT_DEV} /mnt")
        root_mount = ROOT_DEV

    # Mount ESP and create necessary directories
    Path("/mnt/boot").mkdir(parents=True, exist_ok=True) 
    run_command(f"mount {BOOT_DEV} /mnt/boot")
    Path("/mnt/boot/loader/entries").mkdir(parents=True, exist_ok=True)
    Path("/mnt/etc/kernel").mkdir(parents=True, exist_ok=True)
    
    log_print("✓ Disk setup complete")
    return root_mount
# ========== BASE SYSTEM INSTALLATION ==========
def install_base_system():
    log_print("=" * 60)
    log_print("BASE SYSTEM INSTALLATION")
    log_print("=" * 60)
    
    # Build package list: base, headers, firmware, etc.
    base_pkgs = ["base", "base-devel", "linux-firmware", "nano", "sudo", "networkmanager", "git", "plymouth"]
    base_pkgs.extend(KERNELS)
    base_pkgs.extend(KERNEL_HEADERS)
    if ENCRYPTED:
        base_pkgs.append("lvm2")
    
    pkg_str = " ".join(base_pkgs)
    log_print(f"Installing: {pkg_str}")
    
    # Retry loop with mirror refresh
    for attempt in range(1, PACSTRAP_RETRIES + 1):
        log_print(f"--- pacstrap attempt {attempt}/{PACSTRAP_RETRIES} ---")
        try:
            run_command(["pacstrap", "-K", "/mnt"] + base_pkgs)
            log_print("✓ Base system installation successful")
            break
        except subprocess.CalledProcessError:
            if attempt == PACSTRAP_RETRIES:
                log_print("FATAL: pacstrap failed after all retries", is_error=True)
                sys.exit(1)
            log_print(f"pacstrap failed. Refreshing mirrors and retrying...", is_error=True)
            run_command("reflector --latest 30 --protocol https --sort rate --save /etc/pacman.d/mirrorlist")
            run_command("pacman -Syy")
            time.sleep(PACSTRAP_RETRY_DELAY)

# ========== SYSTEM CONFIGURATION ==========
def configure_system(root_mount):
    log_print("=" * 60)
    log_print("SYSTEM CONFIGURATION")
    log_print("=" * 60)
    
    run_command("genfstab -U /mnt > /mnt/etc/fstab")
    
    # Basic settings
    run_chroot("ln -sf /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime")
    run_chroot("hwclock --systohc")
    run_chroot("echo 'en_US.UTF-8 UTF-8' >> /etc/locale.gen")
    run_chroot("echo 'ar_SA.UTF-8 UTF-8' >> /etc/locale.gen")
    run_chroot("locale-gen")
    write_file(Path("/etc/locale.conf"), "LANG=en_US.UTF-8", chroot=True)
    write_file(Path("/etc/vconsole.conf"), "KEYMAP=us", chroot=True)
    write_file(Path("/etc/hostname"), f"{HOSTNAME}\n", chroot=True)
    hosts = f"127.0.0.1\tlocalhost\n::1\t\tlocalhost\n127.0.1.1\t{HOSTNAME}.localdomain\n"
    write_file(Path("/etc/hosts"), hosts, chroot=True)
    
    # Users and passwords
    run_chroot(f"echo 'root:{ROOT_PASS}' | chpasswd")
    run_chroot(f"useradd -m -s /bin/bash {USER}")
    run_chroot(f"echo '{USER}:{USER_PASS}' | chpasswd")
    for group in ["wheel", "audit", "libvirt", "firejail", "network"]:
        run_chroot(f"groupadd -rf {group}")
        run_chroot(f"gpasswd -a {USER} {group}")
    run_chroot("groupadd -rf allow-internet")
    
    # Enable NetworkManager early
    run_chroot("systemctl enable NetworkManager")
    
    log_print("✓ System configuration complete")

# ========== BOOT CONFIGURATION ==========
def configure_boot(root_mount):
    log_print("=" * 60)
    log_print("BOOT CONFIGURATION")
    log_print("=" * 60)
    
    # Get UUIDs for kernel cmdline
    if ENCRYPTED:
        root_uuid = subprocess.run(f"blkid -s UUID -o value {ROOT_DEV}", capture_output=True, text=True, shell=True).stdout.strip()
        # We'll use sd-encrypt hook, so no crypttab.initramfs needed
        # Set mkinitcpio hooks: base systemd plymouth autodetect modconf block sd-encrypt lvm2 filesystems keyboard fsck
        hooks = "base systemd plymouth autodetect modconf block sd-encrypt lvm2 filesystems keyboard fsck"
    else:
        root_uuid = subprocess.run(f"blkid -s UUID -o value {ROOT_DEV}", capture_output=True, text=True, shell=True).stdout.strip()
        hooks = "base systemd plymouth autodetect modconf block filesystems keyboard fsck"
    
    run_chroot(f"sed -i 's/^HOOKS.*/HOOKS=({hooks})/' /etc/mkinitcpio.conf")
    
    # Helper to create boot entries for each installed kernel
    def create_entry(kernel_name, kernel_image, initrd_image, params):
        conf = f"title   {HOSTNAME} - {kernel_name}\n"
        conf += f"linux   /{kernel_image}\n"
        conf += f"initrd  /{initrd_image}\n"
        if ENCRYPTED:
            conf += f"options rd.luks.name={root_uuid}=archy root={root_mount} rw {params}\n"
        else:
            conf += f"options root=UUID={root_uuid} rw {params}\n"
        return conf

    # Map kernel package names to boot files
    kernel_map = {
        "linux-hardened": ("vmlinuz-linux-hardened", "initramfs-linux-hardened.img", "initramfs-linux-hardened-fallback.img", HARDENED_PARAMS),
        "linux-zen":      ("vmlinuz-linux-zen",      "initramfs-linux-zen.img",      "initramfs-linux-zen-fallback.img",      STANDARD_PARAMS),
        "linux-lts":      ("vmlinuz-linux-lts",      "initramfs-linux-lts.img",      "initramfs-linux-lts-fallback.img",      STANDARD_PARAMS),
    }
    
    entries_dir = Path("/mnt/boot/loader/entries")
    default_entry = None
    for pkg, (vmlinuz, initrd, fallback_initrd, params) in kernel_map.items():
        if pkg in KERNELS:
            safe_name = pkg.replace("linux-", "arch-")  # e.g., arch-hardened, arch-zen, arch-lts
            # Main entry
            entry_conf = create_entry(f"Linux {pkg.split('-')[1].capitalize()}", vmlinuz, initrd, params)
            (entries_dir / f"{safe_name}.conf").write_text(entry_conf)
            # Fallback entry (with no extra params for safety)
            fallback_conf = create_entry(f"Linux {pkg.split('-')[1].capitalize()} (fallback)", vmlinuz, fallback_initrd, "")
            (entries_dir / f"{safe_name}-fallback.conf").write_text(fallback_conf)
            if default_entry is None:
                default_entry = f"{safe_name}.conf"

    # Bootloader main config
    loader_conf = f"default {default_entry}\ntimeout 5\nconsole-mode max\neditor no\n"
    write_file(Path("/boot/loader/loader.conf"), loader_conf, chroot=True)
    
    # Kernel cmdline for UKI if ever needed
    if ENCRYPTED:
        cmdline = f"rd.luks.name={root_uuid}=archy root={root_mount} rw {HARDENED_PARAMS}"
    else:
        cmdline = f"root=UUID={root_uuid} rw {HARDENED_PARAMS}"
    write_file(Path("/etc/kernel/cmdline"), cmdline, chroot=True)
    
    log_print("✓ Boot configuration complete")

# ========== PACKAGE INSTALLATION ==========
def install_regular_packages():
    log_print("=" * 60)
    log_print("REGULAR PACKAGES INSTALLATION")
    log_print("=" * 60)
    packages, aur = parse_package_file(PACKAGE_FILE)
    if packages:
        total = len(packages)
        for idx, pkg in enumerate(packages, 1):
            log_print(f"[{idx}/{total}] Installing: {pkg}")
            run_chroot(f"pacman --noconfirm --needed -S {pkg}")
        log_print(f"✓ Installed {total} regular packages")
    else:
        log_print("No regular packages found.")
    return aur

def install_aur_packages(aur_packages):
    log_print("=" * 60)
    log_print("AUR PACKAGES INSTALLATION")
    log_print("=" * 60)
    
    # Optional: install reflector in target system (if you plan to keep mirrors up-to-date)
    run_chroot("pacman --noconfirm --needed -S reflector")
    
    # Grant temporary sudo rights for yay
    run_chroot(f"echo '{USER} ALL=(ALL) NOPASSWD:ALL   # temp-for-yay' >> /etc/sudoers")
    
    # Install yay-bin
    run_chroot(f"su - {USER} -c 'git clone https://aur.archlinux.org/yay-bin.git /home/{USER}/yay-bin'")
    run_chroot(f"su - {USER} -c 'cd /home/{USER}/yay-bin && makepkg -si --noconfirm'")
    run_chroot(f"rm -rf /home/{USER}/yay-bin")
    
    if aur_packages:
        total_aur = len(aur_packages)
        for idx, aurpkg in enumerate(aur_packages, 1):
            log_print(f"[{idx}/{total_aur}] Installing AUR: {aurpkg}")
            run_chroot(f"su - {USER} -c 'yay --noconfirm -S {aurpkg}'")
        log_print(f"✓ Installed {total_aur} AUR packages")
    else:
        log_print("No AUR packages to install.")
    
    # Remove temporary sudo line
    run_chroot("sed -i '/# temp-for-yay$/d' /etc/sudoers")

# ========== POST-INSTALLATION ==========
def post_installation():
    log_print("=" * 60)
    log_print("POST-INSTALLATION TASKS")
    log_print("=" * 60)
    
    # systemd-boot installation
    run_chroot("bootctl install")
    
    # Plymouth theme
    run_chroot("plymouth-set-default-theme -R arch-charge")
    
    # Deploy rootfs overlay if present
    if Path("rootfs_clean").is_dir():
        log_print("Deploying rootfs_clean overlay...")
        run_command("cp -a rootfs_clean/* /mnt/")
        for f in Path("/mnt/usr/local/bin").glob("*"):
            if f.is_file(): f.chmod(0o755)
        # Fix audit_notify user id
        uid = subprocess.run(f"arch-chroot /mnt id -u {USER}", capture_output=True, text=True, shell=True).stdout.strip()
        audit_script = Path("/mnt/usr/local/bin/audit_notify.py")
        if audit_script.exists():
            content = audit_script.read_text()
            content = content.replace("USER_ID = 1000", f"USER_ID = {uid}")
            audit_script.write_text(content)

    # Firejail configuration
    run_chroot("/usr/bin/firecfg")
    firejail_users = Path("/mnt/etc/firejail/firejail.users")
    if firejail_users.exists():
        content = firejail_users.read_text()
        content = content.replace("USER_PLACEHOLDER", USER)
        firejail_users.write_text(content)
    
    # Rebuild all initramfs images (important after hook changes)
    run_chroot("mkinitcpio -P")
    
    log_print("✓ Post-installation tasks complete")

# ========== VERIFICATION ==========
def verify_installation():
    log_print("=" * 60)
    log_print("INSTALLATION VERIFICATION")
    log_print("=" * 60)
    if ENCRYPTED:
        result = subprocess.run(f"blkid {ROOT_DEV} | grep -q 'crypto_LUKS'", shell=True)
        log_print("✓ LUKS verified" if result.returncode == 0 else "⚠ LUKS check failed!")
    
    for pkg in KERNELS:
        try:
            run_chroot(f"pacman -Q {pkg}")
            log_print(f"✓ {pkg} installed")
        except subprocess.CalledProcessError:
            log_print(f"⚠ {pkg} not found", is_error=True)

    log_print("✓ Verification complete")

# ========== FINAL SETUP ==========
def final_setup():
    log_print("=" * 60)
    log_print("FINAL SETUP")
    log_print("=" * 60)
    hypr = Path("install-hyprland-dots.sh")
    if hypr.exists():
        dest = Path(f"/mnt/home/{USER}/install-hyprland-dots.sh")
        shutil.copy(hypr, dest)
        uid = subprocess.run(f"arch-chroot /mnt id -u {USER}", capture_output=True, text=True, shell=True).stdout.strip()
        gid = subprocess.run(f"arch-chroot /mnt id -g {USER}", capture_output=True, text=True, shell=True).stdout.strip()
        if uid and gid:
            os.chown(dest, int(uid), int(gid))
        dest.chmod(0o755)
        log_print("Hyprland dotfile installer copied to user home.")
    log_print(f"Installation complete! Log: {LOG_FILE}")
    log_print("You can reboot now: reboot")

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
    log_print(f"Boot device: {BOOT_DEV}")
    log_print(f"Kernels: {', '.join(KERNELS)}")
    log_print("=" * 60 + "\n")

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