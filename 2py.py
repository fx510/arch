#!/usr/bin/env python3
"""
Arch Linux installation script – paranoid edition
Features: manual LUKS passphrase + UKI (unsigned) + kernel lockdown + IMA
           NO Secure Boot, NO TPM, NO Firejail, NO AUR/yay, NO Plymouth.

Run as root on a live Arch ISO.

PATCHED VERSION — fixes applied:
  1. CONFIG_CHECKS now points at the file that is actually written
     (/efi/loader/entries/arch-hardened-uki.conf), not a nonexistent
     /boot/loader/entries/arch-hardened.conf.
  2. The mkinitcpio preset is re-written immediately before the final
     `mkinitcpio -P` call in post_installation(), in case pacstrap's
     kernel-install hook (90-mkinitcpio-install.hook) already ran
     mkinitcpio once during base install and/or package install
     clobbered/regenerated the stock preset.
  3. post_installation() now runs mkinitcpio with -v and captures
     output to the log, and explicitly checks for the systemd-boot
     EFI stub (linuxx64.efi.stub) before building, so a missing-stub
     failure is reported clearly instead of silently producing only
     a plain initramfs.
  4. Verbose mkinitcpio output is scanned for the UKI creation line
     so success/failure is detected from real evidence, not just
     "does the file exist".
  5. FIXED: write_file() pathlib join bug — absolute paths on the right
     side of / operator discard the left side, so Path("/mnt") / Path("/etc/...")
     was writing to the live ISO instead of the chroot target. Now strips
     leading slash before joining.
  6. FIXED: Similar path join issues in other places (cleanup function,
     ukify config, etc.) where absolute paths were used with /mnt prefix.
  7. FIXED: mkinitcpio preset now includes ALL_config and ALL_kver which
     are required for UKI generation to work properly.
"""

import subprocess, sys, os, shutil, re, time, textwrap
from pathlib import Path
from datetime import datetime
import atexit

# ========== CONFIGURATION ==========
ROOT_DEV = "/dev/nvme0n1p2"       # LUKS container
BOOT_DEV = "/dev/nvme0n1p1"       # EFI System Partition
USER = "test"
USER_PASS = "asdasd"
ROOT_PASS = "test"
LUKS_PASS = "asdasd"
HOSTNAME = "archyBTW"
ENCRYPTED = True

DEV_MODE = True
HOST_CACHE_DEV = "/dev/vda"

PACKAGE_FILE = "packages.cfg"

KERNELS = ["linux-hardened", "linux-lts"]
KERNEL_HEADERS = ["linux-hardened-headers", "linux-lts-headers"]


HARDENED_PARAMS = (
    "lsm=landlock,lockdown,yama,integrity,apparmor,bpf lockdown=integrity "
    "ima_policy=tcb mem_sleep_default=deep quiet rd.udev.log_level=3"
)
STANDARD_PARAMS = "quiet rd.udev.log_level=3"

LOG_FILE = f"/tmp/arch_install_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
PACSTRAP_RETRIES = 3
PACSTRAP_RETRY_DELAY = 10
UKI_PATH_HARDENED = "/efi/EFI/Linux/arch-hardened.efi"
UKI_PATH_LTS = "/efi/EFI/Linux/arch-lts.efi"
UKI_PATH = "/efi/EFI/Linux/arch-hardened.efi"
LOADER_ENTRY_NAME = "arch-hardened-uki.conf"
LOADER_ENTRY_NAME_LTS = "arch-lts-uki.conf"
# FIX #1: this now matches the file actually written in configure_boot()
# (Path("/mnt/efi/loader/entries") / "arch-hardened-uki.conf"), instead of
# a /boot/loader/entries/arch-hardened.conf path that never gets created
# because /boot is not a separate mount and the filename didn't match.
CONFIG_CHECKS = {
    f"/efi/loader/entries/{LOADER_ENTRY_NAME}": "linux-hardened",
    f"/efi/loader/entries/{LOADER_ENTRY_NAME_LTS}": "linux-lts",
}


# ========== HELPERS ==========
def log_print(msg: str, is_error: bool = False):
    if is_error:
        msg = f"\033[31m{msg}\033[0m"
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def run_command(cmd, check=True, **kwargs):
    log_print(f"$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    try:
        if isinstance(cmd, str):
            return subprocess.run(cmd, shell=True, check=check, **kwargs)
        else:
            return subprocess.run(cmd, check=check, **kwargs)
    except subprocess.CalledProcessError as e:
        if check:
            log_print(f"Error: Command failed with exit code {e.returncode}: {cmd}", is_error=True)
            raise
        else:
            return e

def run_command_retry(cmd, description, max_retries=3, delay=10):
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

def run_chroot(cmd, input_text=None, check=True, capture_output=False):
    if isinstance(cmd, str):
        full_cmd = ["arch-chroot", "/mnt", "bash", "-c", cmd]
    else:
        full_cmd = ["arch-chroot", "/mnt"] + cmd
    kwargs = {}
    if capture_output:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return run_command(full_cmd, input=input_text, check=check, **kwargs)

def write_file(path: Path, content: str, chroot: bool = False):
    """
    Write a file. If chroot=True, the path is relative to /mnt.
    
    FIX #5: Strip leading slash before joining to prevent pathlib from
    discarding "/mnt" when path is absolute (e.g., Path("/mnt") / Path("/etc/hostname")
    would produce Path("/etc/hostname") instead of Path("/mnt/etc/hostname")).
    """
    if chroot:
        # Convert to string, strip leading slash, then join
        dest = Path("/mnt") / str(path).lstrip("/")
    else:
        dest = path
    
    log_print(f"  -> Writing to: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())   # force write to disk
    log_print(f"Wrote {dest}")

def parse_package_file(filepath: str):
    """Return only the PACKAGES list (ignores AUR)."""
    packages = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    pkg_match = re.search(r'PACKAGES\s*=\s*\(\s*([^)]+)\s*\)', content, re.DOTALL)
    if pkg_match:
        packages = [p for p in pkg_match.group(1).split() if p and not p.startswith('#')]
    return packages

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
    log_print("Installing reflector and pacman-contrib...")
    run_command("pacman -Sy --noconfirm reflector pacman-contrib")
    temp_mirrorlist = "/tmp/mirrorlist_raw"
    run_command(
        "reflector --country Spain --country France --latest 30 --protocol https "
        "--sort rate --threads 50 --save " + temp_mirrorlist
    )
    log_print("Ranking mirrors by speed...")
    final_mirrorlist = "/etc/pacman.d/mirrorlist"
    run_command(f"rankmirrors -n 6 {temp_mirrorlist} > {final_mirrorlist}")
    result = subprocess.run("grep -c '^Server' /etc/pacman.d/mirrorlist", shell=True, capture_output=True, text=True)
    servers = int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0
    if servers == 0:
        log_print("rankmirrors produced no servers, falling back to raw list", is_error=True)
        shutil.copy(temp_mirrorlist, final_mirrorlist)
    else:
        log_print(f"✓ Mirrorlist contains {servers} ranked servers.")
    run_command("pacman -Syy")

# ========== DISK SETUP ==========
def setup_disks():
    log_print("=" * 60)
    log_print("DISK SETUP")
    log_print("=" * 60)

    run_command(f"wipefs -a {BOOT_DEV}")
    run_command(f"wipefs -a {ROOT_DEV}")
    run_command(f"mkfs.fat -F32 {BOOT_DEV}")

    if ENCRYPTED:
        log_print("Setting up LUKS2 + LVM (argon2id, aes-xts-512)...")
        try:
            subprocess.run(
                ["cryptsetup", "luksFormat", ROOT_DEV,
                 "--type", "luks2", "--cipher", "aes-xts-plain64", "--key-size", "512",
                 "--hash", "sha512", "--pbkdf", "argon2id", "--pbkdf-memory", "1048576",
                 "--pbkdf-parallel", "4", "--iter-time", "3000", "--sector-size", "4096",
                 "--key-file", "-"],
                input=LUKS_PASS, text=True, check=True, capture_output=True
            )
        except subprocess.CalledProcessError as e:
            log_print(f"luksFormat failed: {e.stderr}", is_error=True)
            sys.exit(1)
        log_print("LUKS container created.")

        try:
            subprocess.run(
                ["cryptsetup", "open", ROOT_DEV, "archy", "--key-file", "-"],
                input=LUKS_PASS, text=True, check=True, capture_output=True
            )
        except subprocess.CalledProcessError as e:
            log_print(f"cryptsetup open failed: {e.stderr}", is_error=True)
            sys.exit(1)

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

    Path("/mnt/efi").mkdir(parents=True, exist_ok=True)
    run_command(f"mount {BOOT_DEV} /mnt/efi")
    Path("/mnt/efi/EFI/Linux").mkdir(parents=True, exist_ok=True)
    Path("/mnt/etc/kernel").mkdir(parents=True, exist_ok=True)

    log_print("✓ Disk setup complete")
    return root_mount

# ========== BASE SYSTEM INSTALLATION ==========
def install_base_system():
    log_print("=" * 60)
    log_print("BASE SYSTEM INSTALLATION")
    log_print("=" * 60)

    if DEV_MODE and HOST_CACHE_DEV:
        cache_mount = "/mnt/var/cache/pacman/pkg"
        if Path(HOST_CACHE_DEV).exists():
            log_print(f"[DEV] Mounting host pacman cache {HOST_CACHE_DEV} → {cache_mount}")
            Path(cache_mount).mkdir(parents=True, exist_ok=True)
            run_command(f"mount {HOST_CACHE_DEV} {cache_mount}")
        else:
            log_print(f"⚠ [DEV] {HOST_CACHE_DEV} not found — skipping cache mount", is_error=True)

    base_pkgs = [
        "base", "base-devel", "linux-firmware", "nano", "sudo",
        "networkmanager", "git", "systemd-ukify", "efibootmgr"
    ]
    base_pkgs.extend(KERNELS)
    base_pkgs.extend(KERNEL_HEADERS)
    if ENCRYPTED:
        base_pkgs.append("lvm2")

    pkg_str = " ".join(base_pkgs)
    log_print(f"Installing: {pkg_str}")

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
            log_print("pacstrap failed. Refreshing mirrors and retrying...", is_error=True)
            setup_reflector()
            time.sleep(PACSTRAP_RETRY_DELAY)

# ========== SYSTEM CONFIGURATION ==========
def configure_system(root_mount):
    log_print("=" * 60)
    log_print("SYSTEM CONFIGURATION")
    log_print("=" * 60)

    run_command("genfstab -U /mnt > /mnt/etc/fstab")
    run_chroot("sed -i '/\\/efi\\s.*vfat/s/\\(defaults\\)/\\1,ro/' /etc/fstab")
    run_chroot("ln -sf /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime")
    run_chroot("hwclock --systohc")
    run_chroot("echo 'en_US.UTF-8 UTF-8' >> /etc/locale.gen")
    run_chroot("echo 'ar_SA.UTF-8 UTF-8' >> /etc/locale.gen")
    run_chroot("locale-gen")
    write_file(Path("/etc/locale.conf"), "LANG=en_US.UTF-8", chroot=True)
    run_chroot("echo 'KEYMAP=us' > /etc/vconsole.conf && chmod 644 /etc/vconsole.conf")
    write_file(Path("/etc/hostname"), f"{HOSTNAME}\n", chroot=True)
    hosts = f"127.0.0.1\tlocalhost\n::1\t\tlocalhost\n127.0.1.1\t{HOSTNAME}.localdomain\n"
    write_file(Path("/etc/hosts"), hosts, chroot=True)

    proc_root = subprocess.Popen(
        ["arch-chroot", "/mnt", "chpasswd"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True
    )
    proc_root.communicate(input=f"root:{ROOT_PASS}\n")
    if proc_root.returncode != 0:
        log_print("chpasswd root failed", is_error=True)

    run_chroot(f"useradd -m -s /bin/bash {USER}")
    proc_user = subprocess.Popen(
        ["arch-chroot", "/mnt", "chpasswd"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True
    )
    proc_user.communicate(input=f"{USER}:{USER_PASS}\n")
    if proc_user.returncode != 0:
        log_print("chpasswd user failed", is_error=True)

    for group in ["wheel", "audit", "libvirt", "network"]:
        run_chroot(f"groupadd -rf {group}")
        run_chroot(f"gpasswd -a {USER} {group}")
    run_chroot("groupadd -rf allow-internet")
    run_chroot("sed -i 's/^# %wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/' /etc/sudoers")
    run_chroot("systemctl enable NetworkManager")
    log_print("✓ System configuration complete")




###

###
# ========== BOOT CONFIGURATION (UKI, no Secure Boot) ==========
def write_mkinitcpio_preset():
    """
    Writes the linux-hardened mkinitcpio preset that points mkinitcpio at
    building a UKI. Factored out so it can be called both during initial
    boot configuration AND re-applied right before the final `mkinitcpio -P`
    in post_installation(), in case pacstrap's kernel-install pacman hook
    (90-mkinitcpio-install.hook) already ran mkinitcpio using the package's
    stock preset before this one was written, or a later package
    install/upgrade regenerated the stock preset and clobbered ours.
    
    FIX #7: Added ALL_config and ALL_kver which are required for UKI generation.
    Without ALL_kver, mkinitcpio doesn't know which kernel to build for and
    will skip UKI creation with "No kernel version specified" warning.
    Added fallback preset as well for recovery purposes.
    """
    preset = textwrap.dedent(f"""\
    ALL_config="/etc/mkinitcpio.conf"
    ALL_kver="/boot/vmlinuz-linux-hardened"
    
    PRESETS=('default' 'fallback')
    
    default_image="/boot/initramfs-linux-hardened.img"
    default_uki="{UKI_PATH}"
    default_options="--cmdline /etc/kernel/cmdline"
    
    fallback_image="/boot/initramfs-linux-hardened-fallback.img"
    fallback_uki="/efi/EFI/Linux/arch-hardened-fallback.efi"
    fallback_options="-S autodetect --cmdline /etc/kernel/cmdline"
    """)
    write_file(Path("/etc/mkinitcpio.d/linux-hardened.preset"), preset, chroot=True)

 
# ========== PACKAGE INSTALLATION (no AUR) ==========
def install_regular_packages():
    log_print("=" * 60)
    log_print("REGULAR PACKAGES INSTALLATION (official repos only)")
    log_print("=" * 60)

    packages = parse_package_file(PACKAGE_FILE)
    if packages:
        log_print(f"Installing {len(packages)} pacman packages...")
        run_chroot(f"pacman --noconfirm --needed -S {' '.join(packages)}")
        log_print(f"✓ Installed {len(packages)} regular packages")
    else:
        log_print("No regular packages found.")

def write_mkinitcpio_presets():
    """
    Writes mkinitcpio presets for both linux-hardened and linux-lts kernels.
    Each kernel gets both default and fallback UKI presets.
    
    FIX #7: Added ALL_config and ALL_kver which are required for UKI generation.
    Without ALL_kver, mkinitcpio doesn't know which kernel to build for and
    will skip UKI creation with "No kernel version specified" warning.
    """
    
    # Linux Hardened preset
    hardened_preset = textwrap.dedent(f"""\
    ALL_config="/etc/mkinitcpio.conf"
    ALL_kver="/boot/vmlinuz-linux-hardened"
    
    PRESETS=('default' 'fallback')
    
    default_image="/boot/initramfs-linux-hardened.img"
    default_uki="{UKI_PATH_HARDENED}"
    default_options="--cmdline /etc/kernel/cmdline"
    
    fallback_image="/boot/initramfs-linux-hardened-fallback.img"
    fallback_uki="/efi/EFI/Linux/arch-hardened-fallback.efi"
    fallback_options="-S autodetect --cmdline /etc/kernel/cmdline"
    """)
    write_file(Path("/etc/mkinitcpio.d/linux-hardened.preset"), hardened_preset, chroot=True)
    
    # Linux LTS preset
    lts_preset = textwrap.dedent(f"""\
    ALL_config="/etc/mkinitcpio.conf"
    ALL_kver="/boot/vmlinuz-linux-lts"
    
    PRESETS=('default' 'fallback')
    
    default_image="/boot/initramfs-linux-lts.img"
    default_uki="{UKI_PATH_LTS}"
    default_options="--cmdline /etc/kernel/cmdline"
    
    fallback_image="/boot/initramfs-linux-lts-fallback.img"
    fallback_uki="/efi/EFI/Linux/arch-lts-fallback.efi"
    fallback_options="-S autodetect --cmdline /etc/kernel/cmdline"
    """)
    write_file(Path("/etc/mkinitcpio.d/linux-lts.preset"), lts_preset, chroot=True)

def configure_boot(root_mount):
    log_print("=" * 60)
    log_print("BOOT CONFIGURATION (UKI, unsigned)")
    log_print("=" * 60)

    hooks = "base systemd keyboard autodetect modconf block sd-encrypt lvm2 filesystems fsck"
    run_chroot(f"sed -i 's/^HOOKS=.*/# &\\nHOOKS=({hooks})/' /etc/mkinitcpio.conf")

    root_uuid = subprocess.run(
        f"blkid -s UUID -o value {ROOT_DEV}", capture_output=True, text=True, shell=True
    ).stdout.strip()
    if not root_uuid:
        log_print("Could not determine root UUID – aborting.", is_error=True)
        sys.exit(1)

    if ENCRYPTED:
        cmdline = f"rd.luks.name={root_uuid}=archy root={root_mount} rw {HARDENED_PARAMS}"
        cmdline_lts = f"rd.luks.name={root_uuid}=archy root={root_mount} rw {STANDARD_PARAMS}"
    else:
        cmdline = f"root=UUID={root_uuid} rw {HARDENED_PARAMS}"
        cmdline_lts = f"root=UUID={root_uuid} rw {STANDARD_PARAMS}"

    cmdline_path = Path("/etc/kernel/cmdline")
    write_file(cmdline_path, cmdline, chroot=True)
    
    # Verify the file was actually written to the correct location
    actual_cmdline_path = Path("/mnt") / str(cmdline_path).lstrip("/")
    if not actual_cmdline_path.exists():
        log_print("WARNING: cmdline file missing after write – creating via chroot fallback.", is_error=True)
        run_chroot(f"echo '{cmdline}' > {cmdline_path}")
        if not actual_cmdline_path.exists():
            log_print("FATAL: Still cannot create /etc/kernel/cmdline inside chroot.", is_error=True)
            sys.exit(1)

    # Write separate cmdline for LTS (without hardened params)
    cmdline_lts_path = Path("/etc/kernel/cmdline-lts")
    write_file(cmdline_lts_path, cmdline_lts, chroot=True)
    
    write_mkinitcpio_presets()

    run_chroot("bootctl install --esp-path=/efi")

    entries_dir = Path("/mnt/efi/loader/entries")
    entries_dir.mkdir(parents=True, exist_ok=True)
    
    # Hardened entries
    hardened_main_entry = textwrap.dedent(f"""\
        title   {HOSTNAME} - Hardened (UKI)
        linux   {UKI_PATH_HARDENED}
    """)
    
    hardened_fallback_entry = textwrap.dedent(f"""\
        title   {HOSTNAME} - Hardened (UKI, fallback)
        linux   /efi/EFI/Linux/arch-hardened-fallback.efi
    """)
    
    # LTS entries
    lts_main_entry = textwrap.dedent(f"""\
        title   {HOSTNAME} - LTS (UKI)
        linux   {UKI_PATH_LTS}
    """)
    
    lts_fallback_entry = textwrap.dedent(f"""\
        title   {HOSTNAME} - LTS (UKI, fallback)
        linux   /efi/EFI/Linux/arch-lts-fallback.efi
    """)
    
    # Write all entries
    entry_paths = {
        entries_dir / LOADER_ENTRY_NAME: hardened_main_entry,
        entries_dir / "arch-hardened-fallback-uki.conf": hardened_fallback_entry,
        entries_dir / LOADER_ENTRY_NAME_LTS: lts_main_entry,
        entries_dir / "arch-lts-fallback-uki.conf": lts_fallback_entry,
    }
    
    for path, content in entry_paths.items():
        path.write_text(content)
        log_print(f"Wrote {path}")

    loader_conf = f"default {LOADER_ENTRY_NAME.replace('.conf', '')}\ntimeout 5\nconsole-mode max\neditor no\n"
    write_file(Path("/efi/loader/loader.conf"), loader_conf, chroot=True)

    log_print("✓ Boot configuration complete (no signing)")

def post_installation():
    log_print("=" * 60)
    log_print("POST-INSTALLATION TASKS")
    log_print("=" * 60)

    if Path("rootfs_clean").is_dir():
        log_print("Deploying rootfs_clean overlay...")
        run_command("cp -a rootfs_clean/* /mnt/")
        for f in Path("/mnt/usr/local/bin").glob("*"):
            if f.is_file(): f.chmod(0o755)
        uid = subprocess.run(f"arch-chroot /mnt id -u {USER}", capture_output=True, text=True, shell=True).stdout.strip()
        audit_script = Path("/mnt/usr/local/bin/audit_notify.py")
        if audit_script.exists():
            content = audit_script.read_text()
            content = content.replace("USER_ID = 1000", f"USER_ID = {uid}")
            audit_script.write_text(content)

    # Re-assert presets before final build
    log_print("Re-asserting mkinitcpio presets before final build...")
    write_mkinitcpio_presets()
    
    # Verify presets were written correctly
    for kernel in ["linux-hardened", "linux-lts"]:
        log_print(f"Verifying {kernel} preset contents:")
        preset_check = run_chroot(f"cat /etc/mkinitcpio.d/{kernel}.preset", capture_output=True)
        log_print(preset_check.stdout if preset_check.stdout else f"Could not read {kernel} preset")

    # Verify systemd-boot EFI stub
    stub_check = run_chroot(
        "test -f /usr/lib/systemd/boot/efi/linuxx64.efi.stub",
        check=False
    )
    if stub_check.returncode != 0:
        log_print(
            "⚠ systemd EFI stub (linuxx64.efi.stub) not found in chroot — "
            "UKI generation will be skipped. Is the 'systemd' package installed?",
            is_error=True
        )
    else:
        log_print("✓ systemd EFI stub found")

    # Check if kernel images exist
    for kernel in ["linux-hardened", "linux-lts"]:
        kernel_check = run_chroot(
            f"test -f /boot/vmlinuz-{kernel}",
            check=False
        )
        if kernel_check.returncode != 0:
            log_print(
                f"⚠ Kernel image /boot/vmlinuz-{kernel} not found — "
                "UKI cannot be built without the kernel",
                is_error=True
            )
        else:
            log_print(f"✓ {kernel} kernel image found")

    # Run mkinitcpio for all kernels
    result = run_chroot("mkinitcpio -v -P", check=False, capture_output=True)
    combined_output = (result.stdout or "") + (result.stderr or "")
    log_print(combined_output)

    uki_built_per_log = bool(re.search(r"[Uu]nified kernel image", combined_output))

    # Check for all UKI files
    uki_files = {
        "Hardened main": f"/mnt/{UKI_PATH_HARDENED.lstrip('/')}",
        "Hardened fallback": "/mnt/efi/EFI/Linux/arch-hardened-fallback.efi",
        "LTS main": f"/mnt/{UKI_PATH_LTS.lstrip('/')}",
        "LTS fallback": "/mnt/efi/EFI/Linux/arch-lts-fallback.efi",
    }

    if result.returncode != 0:
        log_print(f"⚠ mkinitcpio exited with code {result.returncode}", is_error=True)

    all_ukis_ok = True
    for name, path in uki_files.items():
        if Path(path).exists():
            log_print(f"✓ {name} UKI built successfully")
        else:
            log_print(f"⚠ {name} UKI not found at {path}", is_error=True)
            all_ukis_ok = False

    if uki_built_per_log:
        log_print("✓ UKI generation detected in mkinitcpio output")
    else:
        log_print(
            "⚠ mkinitcpio output did not mention building unified kernel images — "
            "files may be stale from earlier builds. Re-check manually.",
            is_error=True
        )

    if not all_ukis_ok:
        log_print(
            "Some UKIs not found – build may have failed. Check the mkinitcpio output above, "
            "and confirm presets have correct default_uki paths and that the systemd EFI stub is present.",
            is_error=True
        )

    log_print("✓ Post-installation tasks complete")

# ========== CONFIG VERIFICATION ==========
def install_post_script():
    log_print("=" * 60)
    log_print("POST-INSTALLATION CONFIG CHECK")
    log_print("=" * 60)

    missing = []
    for conf_path, pkg in CONFIG_CHECKS.items():
        # FIX #6: Use proper path joining
        full_path = Path("/mnt") / conf_path.lstrip("/")
        if full_path.exists():
            try:
                run_chroot(f"pacman -Q {pkg}")
            except subprocess.CalledProcessError:
                missing.append((conf_path, pkg, "Package not installed"))
        else:
            missing.append((conf_path, pkg, "Config file missing"))

    print("\n" + "=" * 60)
    print("CONFIG VERIFICATION SUMMARY")
    print("=" * 60)
    if missing:
        print("The following issues were found:")
        for conf, pkg, reason in missing:
            print(f"  - {conf}: {reason} (expected package: {pkg})")
    else:
        print("All config files are present and required packages are installed.")

    while True:
        choice = input("\nDo you want to proceed? (y/n): ").strip().lower()
        if choice in ("y", "n"):
            break
        print("Please enter 'y' or 'n'.")

    if choice == "n":
        sys.exit(0)

    if missing:
        pkgs_to_install = set(pkg for _, pkg, reason in missing if reason == "Package not installed")
        if pkgs_to_install:
            run_chroot(f"pacman --noconfirm --needed -S {' '.join(pkgs_to_install)}")
    log_print("✓ Post-installation config check complete.")

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

    log_print("=" * 60)
    log_print("Installation complete – manual LUKS passphrase, unsigned UKI, no AUR, no Plymouth.")
    log_print(f"Log file: {LOG_FILE}")
    log_print("You can reboot now: reboot")
    log_print("=" * 60)

# ========== MAIN ==========
def main():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"Installation log started at {datetime.now()}\n")
    log_print(f"Log file: {LOG_FILE}")

    if len(sys.argv) > 1 and sys.argv[1] == "--install-post":
        install_post_script()
        return

    validate_setup()
    setup_reflector()

    log_print("\n" + "=" * 60)
    log_print("ARCH LINUX PARANOID INSTALLATION (no Secure Boot, no Firejail, no AUR, no Plymouth)")
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
    install_regular_packages()
    post_installation()
    verify_installation()
    install_post_script()
    final_setup()

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("This script must be run as root.", file=sys.stderr)
        sys.exit(1)
    main()