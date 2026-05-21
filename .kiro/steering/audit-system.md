# Audit System - Binaries and Monitoring

## Overview

The audit system provides real-time security monitoring through the Linux Audit Framework (auditd). It monitors sensitive files, detects suspicious behavior, and sends desktop notifications for security events.

## Core Binaries Used

### 1. Audit Daemon Binaries (System)

#### Monitored for Tampering (Execution Tracked)
- **`/usr/bin/auditd`**: Main audit daemon
  - **Monitored by**: `/etc/audit/rules.d/10-files.rules` (execute permission, key: `auditd_tampering`)
  - **Purpose**: Core audit logging daemon
  - **Alert**: "AUDITD TAMPERING" if executed by logged-in user

- **`/usr/bin/auditctl`**: Audit control utility
  - **Monitored by**: `/etc/audit/rules.d/10-files.rules` (execute permission, key: `auditd_tampering`)
  - **Purpose**: Load/modify audit rules at runtime
  - **Alert**: "AUDITD TAMPERING" if executed by logged-in user

- **`/usr/bin/augenrules`**: Audit rules generator
  - **Monitored by**: `/etc/audit/rules.d/10-files.rules` (execute permission, key: `auditd_tampering`)
  - **Purpose**: Compile audit rules from `/etc/audit/rules.d/`
  - **Alert**: "AUDITD TAMPERING" if executed by logged-in user

#### Used by Monitoring Scripts (Not Monitored)
- **`/usr/bin/ausearch`**: Search audit logs
  - **Called by**: Legacy monitoring scripts (not actively used in current system)
  - **Purpose**: Query audit log for specific events
  - **Usage**: `ausearch -f /etc/passwd`

### 2. Custom Monitoring Scripts (Python)

- **`/usr/local/bin/auditd-notify`**: Real-time audit log monitor
  - **Language**: Python 3 (shebang: `#!/usr/bin/python3 -u`)
  - **Type**: Long-running daemon
  - **Reads**: `/var/log/audit/audit.log`
  - **Reads**: `/proc/stat` (for boot time detection)
  - **Calls**: `os.stat()`, `os.lstat()`, `open()`, `time.sleep()`
  - **Outputs**: JSON notifications to stdout (captured by systemd)
  - **Service**: `auditd-notify.service`

- **`/usr/local/bin/auditor`**: Periodic security audit script
  - **Language**: Python 3 (shebang: `#!/usr/bin/python3 -u`)
  - **Type**: One-shot (runs and exits)
  - **Calls**: Multiple binaries (see below)
  - **Outputs**: JSON notifications to stdout
  - **Service**: `auditor.service` (triggered by `auditor.timer`)

### 3. Notification Binaries

- **`notify-send`**: Desktop notification sender (libnotify)
  - **Called by**: `journalctl-notify` user service
  - **Package**: `libnotify`
  - **Purpose**: Send notifications to notification daemon
  - **Usage**: `notify-send -u critical "Title" "Message"`

- **Dunst**: Notification daemon
  - **Package**: `dunst`
  - **Purpose**: Display desktop notifications
  - **Receives**: Notifications from `notify-send`

### 4. Disk Space Management Scripts (Called by auditd)

- **`/usr/local/bin/notify-low-on-disk-space`**: Low space notifier
  - **Called by**: `auditd.conf` (`space_left_action`)
  - **Trigger**: When disk space falls below 500MB
  - **Purpose**: Alert user of low disk space

- **`/usr/local/bin/try-to-fix-low-on-disk-space`**: Auto cleanup
  - **Called by**: `auditd.conf` (`admin_space_left_action`, `disk_full_action`)
  - **Trigger**: When disk space falls below 100MB or disk is full
  - **Calls**:
    - **`paccache -rk2`**: Clean pacman cache (keep last 2 versions)
    - **`journalctl --vacuum-time=7d`**: Clean journal logs (keep last 7 days)
    - **`pacman -Qtdq | pacman -Rns -`**: Remove orphaned packages
    - **`df /`**: Check available disk space
    - **`awk`**: Parse df output
  - **Outputs**: JSON notification with freed space

- **`/usr/local/bin/notify-disk-error`**: Disk error notifier
  - **Called by**: `auditd.conf` (`disk_error_action`)
  - **Trigger**: When disk errors occur
  - **Purpose**: Alert user of disk errors

### 5. System Binaries Used by Auditor

#### Package Management
- **`/usr/bin/pacman -Qn`**: List installed packages
  - **Called by**: `auditor` (`check_local_cves()`)
  - **Purpose**: Get list of installed packages for CVE comparison
  - **Whitelisted**: Excluded from `auditd_tampering` alerts

- **`/usr/bin/vercmp`**: Version comparison
  - **Called by**: `auditor` (`vercmp()` function)
  - **Purpose**: Compare package versions (e.g., `vercmp 1.2.3 1.2.4` returns -1)
  - **Usage**: Determine if installed version is vulnerable

#### Python Standard Library
- **`/usr/bin/python3`**: Python interpreter
  - **Used by**: All Python scripts
  - **Modules used**:
    - `os`: File system operations (`os.stat()`, `os.lstat()`, `os.listdir()`, `os.path.join()`)
    - `sys`: System operations (`sys.exit()`, `sys.stdout`)
    - `json`: JSON parsing/generation
    - `stat`: File permission constants (`S_ISDIR`, `S_ISREG`, `S_IWOTH`, `S_IXOTH`, `S_IRWXO`)
    - `subprocess`: Execute external commands (`run()`, `check_output()`)
    - `requests`: HTTP requests (fetch CVE data)
    - `time`: Sleep and timing (`time.sleep()`)
    - `re`: Regular expressions (parse audit logs)
    - `traceback`: Error reporting (`format_exc()`)

#### System Information Files
- **`/proc/stat`**: Boot time detection
  - **Read by**: `auditd-notify` (`follow_auditd_events()`)
  - **Purpose**: Determine system boot time to skip old audit events
  - **Field used**: `btime` (boot time in seconds since epoch)

- **`/sys/firmware/efi/efivars/SecureBoot-*`**: Secure boot status
  - **Read by**: `auditor` (`check_secure_boot()`)
  - **Purpose**: Verify secure boot is enabled
  - **Byte checked**: `content[4] == 1` (secure boot enabled)

- **`/etc/group`**: Group membership
  - **Read by**: `auditor` (`check_docker()`)
  - **Purpose**: Check for users in docker group

- **`/etc/cve-ignore.list`**: CVE ignore list
  - **Read by**: `auditor` (`check_local_cves()`)
  - **Purpose**: Skip CVEs that are not relevant to the user
  - **Format**: One CVE per line, `#` for comments

#### Network (HTTP)
- **`https://security.archlinux.org/issues/all.json`**: CVE database
  - **Fetched by**: `auditor` (`check_local_cves()`)
  - **Method**: `requests.get()`
  - **Purpose**: Get list of known CVEs for Arch Linux packages

## Files and Paths Monitored

### Critical System Files (Real-time Monitoring)

#### 1. Password Database
```
-w /etc/shadow -p wa -F auid!=unset -k etc_shadow
```
- **Path**: `/etc/shadow`
- **Permissions**: Write, Attribute change
- **Key**: `etc_shadow`
- **Trigger**: Any logged-in user accessing password hashes
- **Notification**: "SECRET FILE ACCESS"

#### 2. Rootkit Detection
```
-w /etc/ld.so.preload -p wa -F auid!=unset -k etc_ld_so_preload
```
- **Path**: `/etc/ld.so.preload`
- **Permissions**: Write, Attribute change
- **Key**: `etc_ld_so_preload`
- **Trigger**: System-wide library preloading (typical rootkit behavior)
- **Notification**: "ROOTKIT BEHAVIOR DETECTED"

#### 3. Secure Boot Protection
```
-w /usr/bin/arch-secure-boot -p wa -F auid!=unset -k secure_boot_manager
-w /etc/arch-secure-boot/keys -p rwa -F auid!=unset -k secure_boot_keys
-w /etc/secureboot/keys -p rwa -F auid!=unset -k secure_boot_keys
-w /efi -p wa -F auid!=unset -k efi_boot
```
- **Paths**: 
  - `/usr/bin/arch-secure-boot`
  - `/etc/arch-secure-boot/keys`
  - `/etc/secureboot/keys`
  - `/efi`
- **Permissions**: Read, Write, Attribute change
- **Key**: `secure_boot_keys`, `secure_boot_manager`, `efi_boot`
- **Trigger**: Access to secure boot keys or EFI partition
- **Notification**: "SECRET FILE ACCESS" (excludes `/usr/bin/sbsign` and `/usr/bin/find`)

#### 4. Audit System Self-Protection
```
-w /var/log/audit/ -p wa -F auid!=unset -k auditd_tampering
-w /etc/audit/ -p wa -F auid!=unset -k auditd_tampering
-w /etc/libaudit.conf -p wa -F auid!=unset -k auditd_tampering
-w /usr/bin/auditctl -p x -F auid!=unset -k auditd_tampering
-w /usr/bin/auditd -p x -F auid!=unset -k auditd_tampering
-w /usr/bin/augenrules -p x -F auid!=unset -k auditd_tampering
```
- **Paths**: 
  - `/var/log/audit/`
  - `/etc/audit/`
  - `/etc/libaudit.conf`
  - `/usr/bin/auditctl`
  - `/usr/bin/auditd`
  - `/usr/bin/augenrules`
- **Permissions**: Write, Attribute change, Execute
- **Key**: `auditd_tampering`
- **Trigger**: Attempts to modify audit configuration or logs
- **Notification**: "AUDITD TAMPERING" (excludes `/usr/bin/pacman`)

#### 5. Privilege Abuse Detection
```
-a always,exit -F dir=/home/ -F arch=b32 -S open,openat,openat2,getdents,getdents64,mkdir,mkdirat,rmdir,unlink,unlinkat -F uid=0 -F auid>=1000 -F auid!=unset -C auid!=obj_uid -k power_abuse
-a always,exit -F dir=/home/ -F arch=b64 -S open,openat,openat2,getdents,getdents64,mkdir,mkdirat,rmdir,unlink,unlinkat -F uid=0 -F auid>=1000 -F auid!=unset -C auid!=obj_uid -k power_abuse
```
- **Path**: `/home/` (all user directories)
- **Syscalls Monitored**: 
  - `open`, `openat`, `openat2`
  - `getdents`, `getdents64`
  - `mkdir`, `mkdirat`
  - `rmdir`, `unlink`, `unlinkat`
- **Condition**: Root process (uid=0) accessing another user's home directory
- **Key**: `power_abuse`
- **Trigger**: Privileged process accessing user files
- **Notification**: "PRIVILEGED PROCESS USING HOME DIRECTORY"

## Event Types Monitored

### 1. AppArmor Denials
- **Type**: `AVC`
- **Condition**: `apparmor="DENIED"`
- **Notification**: "APPARMOR DENIAL"
- **Info**: Profile name, operation, file path, user, denied permissions

### 2. Firejail Seccomp Denials
- **Type**: `SECCOMP`
- **Condition**: `subj` contains "firejail"
- **Notification**: "FIREJAIL DENIAL (SECCOMP)"
- **Info**: Program path, PID, user

### 3. Program Crashes
- **Type**: `ANOM_ABEND`
- **Condition**: `subj` contains "firejail"
- **Notification**: "PROGRAM CRASHED (COREDUMP)"
- **Info**: Program path, PID, signal number, user

### 4. Promiscuous Mode
- **Type**: `ANOM_PROMISCUOUS`
- **Condition**: `prom != "0"`
- **Notification**: "INTERFACE IN PROMISCUOUS MODE"
- **Info**: Interface name, user
- **Warning**: "Someone might be listening to your network traffic!"

### 5. Authentication Failures
- **Type**: `USER_AUTH`
- **Condition**: `res="failed"`
- **Notification**: "AUTHENTICATION FAILURE"
- **Info**: User, program used

### 6. Syscall Events (File Access)
- **Type**: `SYSCALL`
- **Keys**: `etc_shadow`, `secure_boot_keys`, `etc_ld_so_preload`, `auditd_tampering`, `power_abuse`
- **Notifications**: Various (see above)
- **Info**: Path, user, program, syscall name, success status

## Excluded Events (Noise Reduction)

The following message types are filtered out to prevent spam:

```
-a exclude,always -F msgtype=BPF
-a exclude,always -F msgtype=USER_START
-a exclude,always -F msgtype=USER_END
-a exclude,always -F msgtype=CWD
-a exclude,always -F msgtype=PATH
-a exclude,always -F msgtype=USER_ACCT
-a exclude,always -F msgtype=CRED_REFR
-a exclude,always -F msgtype=CRED_DISP
-a exclude,always -F msgtype=CRED_ACQ
-a exclude,always -F msgtype=NETFILTER_CFG
-a exclude,always -F msgtype=EXECVE
-a exclude,always -F msgtype=SERVICE_START
-a exclude,always -F msgtype=SERVICE_STOP
```

**Rationale**: These events are either too noisy or monitored through other means (e.g., systemd services via journalctl).

## Auditor Script - Periodic Security Checks

The `auditor` script runs weekly via `auditor.timer` and performs comprehensive security audits.

### Binaries Called by Auditor

1. **`/usr/bin/pacman -Qn`**: List installed packages
2. **`/usr/bin/vercmp`**: Compare package versions
3. **Python stdlib**: `os`, `sys`, `json`, `stat`, `subprocess`
4. **`requests` library**: Fetch CVE data from `https://security.archlinux.org/issues/all.json`

### Checks Performed

#### 1. World-Writable Files
- **Function**: `check_world_writable()`
- **Scans**: Entire filesystem (excluding `/proc`, `/sys`, `/dev`, `/run`, `/tmp`)
- **Detects**: Files with `o+w` permission
- **Notification**: "DANGEROUS PERMISSIONS DETECTED"

#### 2. Home Directory Permissions
- **Function**: `check_homes_permission()`
- **Scans**: `/home/*` and `/root`
- **Detects**: Any permissions for "others" (o+rwx)
- **Notification**: "DANGEROUS PERMISSIONS DETECTED"

#### 3. Docker Group Membership
- **Function**: `check_docker()`
- **Reads**: `/etc/group`
- **Detects**: Users in docker group (equivalent to root access)
- **Notification**: "DANGEROUS GROUP DETECTED"

#### 4. Secure Boot Status
- **Function**: `check_secure_boot()`
- **Reads**: `/sys/firmware/efi/efivars/SecureBoot-*`
- **Detects**: Secure boot disabled
- **Notification**: "SECURE BOOT DISABLED"

#### 5. Local CVE Detection
- **Function**: `check_local_cves()`
- **Calls**: `/usr/bin/pacman -Qn`, `/usr/bin/vercmp`
- **Fetches**: `https://security.archlinux.org/issues/all.json`
- **Compares**: Installed package versions against known CVEs
- **Ignores**: CVEs listed in `/etc/cve-ignore.list`
- **Notification**: "VULNERABLE PACKAGES DETECTED"

## Systemd Services

### auditd-notify.service
```
[Unit]
Description=Start the script that will monitor /var/log/audit.log and log relevant things

[Service]
Type=simple
ExecStart=/usr/local/bin/auditd-notify
Restart=on-failure
RestartSec=3s

[Install]
WantedBy=multi-user.target
```
- **Type**: Long-running daemon
- **Restart**: Automatic on failure (3s delay)
- **Reads**: `/var/log/audit/audit.log`
- **Outputs**: JSON notifications to stdout

### auditor.service
```
[Unit]
Description=Run security audit checks

[Service]
Type=oneshot
ExecStart=/usr/local/bin/auditor
```
- **Type**: One-shot (runs and exits)
- **Triggered by**: `auditor.timer` (weekly)

### auditor.timer
```
[Unit]
Description=Run security audits weekly

[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=timers.target
```
- **Schedule**: Weekly
- **Persistent**: Runs missed executions after boot

## Notification Flow

```
Audit Event → auditd → /var/log/audit/audit.log
                              ↓
                    auditd-notify (Python)
                              ↓
                    parse_auditd_entry()
                              ↓
                    notify_if_relevant()
                              ↓
                    print("NOTIFY", json.dumps(...))
                              ↓
                    systemd captures stdout
                              ↓
                    journalctl-notify (user service)
                              ↓
                    notify-send (libnotify)
                              ↓
                    Dunst (notification daemon)
                              ↓
                    Desktop Notification
```

## Log Files

- **Audit Log**: `/var/log/audit/audit.log`
- **Format**: `ENRICHED` (includes human-readable field names)
- **Rotation**: 3 log files, 10MB each
- **Group**: `audit` (users in audit group can read logs)

## Immutability

```
-e 2
```
Audit rules are made immutable at runtime. They cannot be changed without rebooting the system. This prevents attackers from disabling monitoring.

## Complete Binary Reference

### Category 1: Monitored Binaries (Execution Tracked by Audit Rules)

| Binary | Rule File | Permission | Key | Alert Type | Whitelisted |
|--------|-----------|------------|-----|------------|-------------|
| `/usr/bin/auditd` | `10-files.rules` | Execute (x) | `auditd_tampering` | AUDITD TAMPERING | `/usr/bin/pacman` |
| `/usr/bin/auditctl` | `10-files.rules` | Execute (x) | `auditd_tampering` | AUDITD TAMPERING | `/usr/bin/pacman` |
| `/usr/bin/augenrules` | `10-files.rules` | Execute (x) | `auditd_tampering` | AUDITD TAMPERING | `/usr/bin/pacman` |
| `/usr/bin/arch-secure-boot` | `10-files.rules` | Write/Attr (wa) | `secure_boot_manager` | SECRET FILE ACCESS | None |
| `/usr/bin/sbsign` | N/A | N/A | N/A | N/A | Whitelisted for `secure_boot_keys` |
| `/usr/bin/find` | N/A | N/A | N/A | N/A | Whitelisted for `secure_boot_keys` |

### Category 2: Called by Monitoring Scripts

#### By auditd-notify (Real-time Monitor)
| Binary/File | Purpose | Function | Return Value |
|-------------|---------|----------|--------------|
| `/proc/stat` | Boot time detection | `follow_auditd_events()` | `btime` field (seconds since epoch) |
| `/var/log/audit/audit.log` | Audit log reading | `follow_auditd_events()` | Audit events (text stream) |
| Python stdlib: `os.stat()` | File metadata | `reopen_logfile_if_needed()` | File size, inode number |
| Python stdlib: `os.lstat()` | File metadata (no symlink follow) | N/A | File metadata |
| Python stdlib: `time.sleep()` | Polling delay | `follow_auditd_events()` | None (1 second sleep) |
| Python stdlib: `re.search()` | Parse audit entries | `parse_auditd_entry()` | Regex match object |
| Python stdlib: `json.dumps()` | Notification formatting | `notify()` | JSON string |

#### By auditor (Periodic Security Audit)
| Binary/File | Purpose | Function | Return Value |
|-------------|---------|----------|--------------|
| `/usr/bin/pacman -Qn` | List installed packages | `check_local_cves()` | Package list (name version) |
| `/usr/bin/vercmp` | Version comparison | `vercmp()` | -1 (older), 0 (equal), 1 (newer) |
| `/etc/group` | Group membership check | `check_docker()` | Group entries |
| `/etc/cve-ignore.list` | CVE ignore list | `check_local_cves()` | List of CVEs to skip |
| `/sys/firmware/efi/efivars/SecureBoot-*` | Secure boot status | `check_secure_boot()` | Byte 4: 0 (disabled), 1 (enabled) |
| `https://security.archlinux.org/issues/all.json` | CVE database | `check_local_cves()` | JSON array of CVE entries |
| Python stdlib: `os.listdir()` | Directory listing | Multiple functions | List of filenames |
| Python stdlib: `os.stat()` | File metadata | `check_world_writable()`, `check_homes_permission()` | File mode, permissions |
| Python stdlib: `os.lstat()` | File metadata (no symlink) | `check_world_writable()` | File mode, permissions |
| Python stdlib: `subprocess.check_output()` | Execute commands | `vercmp()`, `check_local_cves()` | Command output (bytes) |
| Python stdlib: `requests.get()` | HTTP GET request | `check_local_cves()` | Response object with JSON |

#### By try-to-fix-low-on-disk-space (Disk Cleanup)
| Binary | Purpose | Arguments | Output |
|--------|---------|-----------|--------|
| `paccache` | Clean pacman cache | `-rk2` (keep last 2 versions) | Freed space |
| `journalctl` | Clean journal logs | `--vacuum-time=7d` (keep last 7 days) | Freed space |
| `pacman` | Remove orphaned packages | `-Qtdq \| pacman -Rns - --noconfirm` | Removed packages |
| `df` | Check disk space | `/` (root partition) | Available space |
| `awk` | Parse df output | `'{print $4}'` (available column) | Available KB |

### Category 3: Notification Stack

| Component | Type | Called By | Calls | Purpose |
|-----------|------|-----------|-------|---------|
| `auditd-notify` | Python script | systemd | `print()` → stdout | Parse audit log, emit JSON |
| `auditor` | Python script | systemd timer | `print()` → stdout | Run security checks, emit JSON |
| systemd | Service manager | N/A | Captures stdout | Collect JSON notifications |
| `journalctl-notify` | User service | systemd | `notify-send` | Forward notifications to desktop |
| `notify-send` | Binary | Scripts | D-Bus | Send notification to daemon |
| Dunst | Notification daemon | D-Bus | Display | Show desktop notification |

### Category 4: Disk Space Management (Called by auditd.conf)

| Script | Trigger | auditd.conf Setting | Threshold | Action |
|--------|---------|---------------------|-----------|--------|
| `notify-low-on-disk-space` | Low space | `space_left_action` | 500 MB | Alert user |
| `try-to-fix-low-on-disk-space` | Critical space | `admin_space_left_action` | 100 MB | Auto cleanup |
| `try-to-fix-low-on-disk-space` | Disk full | `disk_full_action` | 0 MB | Auto cleanup |
| `notify-disk-error` | Disk error | `disk_error_action` | N/A | Alert user |

### Category 5: Python Standard Library Modules

| Module | Functions Used | Purpose | Used By |
|--------|----------------|---------|---------|
| `os` | `stat()`, `lstat()`, `listdir()`, `path.join()`, `geteuid()` | File system operations | All scripts |
| `sys` | `exit()`, `stdout` | System operations | All scripts |
| `json` | `dumps()`, `loads()` | JSON serialization | All scripts |
| `stat` | `S_ISDIR`, `S_ISREG`, `S_IWOTH`, `S_IXOTH`, `S_IRWXO` | File permission constants | `auditor` |
| `subprocess` | `run()`, `check_output()`, `CalledProcessError` | Execute external commands | `auditor` |
| `requests` | `get()` | HTTP requests | `auditor` |
| `time` | `sleep()` | Timing and delays | `auditd-notify` |
| `re` | `search()`, `findall()` | Regular expressions | `auditd-notify` |
| `traceback` | `format_exc()` | Error reporting | `auditd-notify` |
| `io` | `TextIOWrapper` | File I/O | `auditd-notify` |
| `typing` | `Iterable`, `Tuple`, `List` | Type hints | All scripts |

### Category 6: System Files Read/Written

| File/Directory | Access Type | Monitored By | Purpose | Alert |
|----------------|-------------|--------------|---------|-------|
| `/etc/shadow` | Write/Attr (wa) | Audit rules | Password hashes | SECRET FILE ACCESS |
| `/etc/ld.so.preload` | Write/Attr (wa) | Audit rules | Library preloading | ROOTKIT BEHAVIOR DETECTED |
| `/etc/arch-secure-boot/keys` | Read/Write/Attr (rwa) | Audit rules | Secure boot keys | SECRET FILE ACCESS |
| `/etc/secureboot/keys` | Read/Write/Attr (rwa) | Audit rules | Secure boot keys | SECRET FILE ACCESS |
| `/efi` | Write/Attr (wa) | Audit rules | EFI partition | SECRET FILE ACCESS |
| `/var/log/audit/` | Write/Attr (wa) | Audit rules | Audit logs | AUDITD TAMPERING |
| `/etc/audit/` | Write/Attr (wa) | Audit rules | Audit config | AUDITD TAMPERING |
| `/etc/libaudit.conf` | Write/Attr (wa) | Audit rules | Audit library config | AUDITD TAMPERING |
| `/home/` | Syscalls (open, mkdir, etc.) | Audit rules | User directories | PRIVILEGED PROCESS USING HOME DIRECTORY |
| `/proc/stat` | Read | `auditd-notify` | Boot time | None |
| `/sys/firmware/efi/efivars/SecureBoot-*` | Read | `auditor` | Secure boot status | SECURE BOOT DISABLED |
| `/etc/group` | Read | `auditor` | Group membership | DANGEROUS GROUP DETECTED |
| `/etc/cve-ignore.list` | Read | `auditor` | CVE ignore list | None |
| `/var/log/audit/audit.log` | Read | `auditd-notify` | Audit events | None |

### Category 7: Network Endpoints

| URL | Method | Called By | Purpose | Response Format |
|-----|--------|-----------|---------|-----------------|
| `https://security.archlinux.org/issues/all.json` | GET | `auditor` | Fetch CVE database | JSON array |

### Category 8: Syscalls Monitored

| Syscall | Architecture | Monitored Path | Condition | Key | Alert |
|---------|--------------|----------------|-----------|-----|-------|
| `open` | b32, b64 | `/home/` | uid=0, auid>=1000 | `power_abuse` | PRIVILEGED PROCESS USING HOME DIRECTORY |
| `openat` | b32, b64 | `/home/` | uid=0, auid>=1000 | `power_abuse` | PRIVILEGED PROCESS USING HOME DIRECTORY |
| `openat2` | b32, b64 | `/home/` | uid=0, auid>=1000 | `power_abuse` | PRIVILEGED PROCESS USING HOME DIRECTORY |
| `getdents` | b32, b64 | `/home/` | uid=0, auid>=1000 | `power_abuse` | PRIVILEGED PROCESS USING HOME DIRECTORY |
| `getdents64` | b32, b64 | `/home/` | uid=0, auid>=1000 | `power_abuse` | PRIVILEGED PROCESS USING HOME DIRECTORY |
| `mkdir` | b32, b64 | `/home/` | uid=0, auid>=1000 | `power_abuse` | PRIVILEGED PROCESS USING HOME DIRECTORY |
| `mkdirat` | b32, b64 | `/home/` | uid=0, auid>=1000 | `power_abuse` | PRIVILEGED PROCESS USING HOME DIRECTORY |
| `rmdir` | b32, b64 | `/home/` | uid=0, auid>=1000 | `power_abuse` | PRIVILEGED PROCESS USING HOME DIRECTORY |
| `unlink` | b32, b64 | `/home/` | uid=0, auid>=1000 | `power_abuse` | PRIVILEGED PROCESS USING HOME DIRECTORY |
| `unlinkat` | b32, b64 | `/home/` | uid=0, auid>=1000 | `power_abuse` | PRIVILEGED PROCESS USING HOME DIRECTORY |

**Note**: All syscalls require `auid!=unset` (logged-in user) and `auid!=obj_uid` (accessing another user's files).
