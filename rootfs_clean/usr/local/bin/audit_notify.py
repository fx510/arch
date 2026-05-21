#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
====================================================================
 auditd-notify with Telegram support
====================================================================
"""

import os
import re
import sys
import pwd
import time
import json
import logging
import subprocess
from urllib.request import Request, urlopen
from urllib.error import URLError

# ============================================================
# CONFIGURATION
# ============================================================

USER_ID = 1000
NOTIFY_TIMEOUT = "5000"
EVENT_BUFFER_TIMEOUT = 0.40

# Telegram configuration
TELEGRAM_ENABLED = True          # Set to True to enable Telegram notifications
TELEGRAM_BOT_TOKEN = "8135395762:AAFvweL_sLJp4g9shWyEI9bJQVy6QLxNlhQ"
TELEGRAM_CHAT_ID = "1106954164"

IGNORE_EXECUTABLES = {
    "/usr/bin/runuser",
    "/usr/bin/notify-send",
    "/usr/bin/dbus-send",
}

IGNORE_COMM = {
    "systemd",
    "systemd-logind",
    "dbus-daemon",
}

RULES = {
    "identity": {"title": "Identity database modified", "urgency": "critical"},
    "sudo_config": {"title": "sudo configuration modified", "urgency": "critical"},
    "sshd_config": {"title": "SSH configuration modified", "urgency": "critical"},
    "pam_config": {"title": "PAM configuration modified", "urgency": "critical"},
    "privilege_escalation": {"title": "Privilege escalation tool executed", "urgency": "normal"},
    "uid_change": {"title": "UID change detected", "urgency": "low"},
    "gid_change": {"title": "GID change detected", "urgency": "low"},
    "root_command": {"title": "Root command executed", "urgency": "normal"},
    "kernel_modules": {"title": "Kernel module configuration modified", "urgency": "critical"},
    "kernel_module_activity": {"title": "Kernel module activity detected", "urgency": "critical"},
    "ld_so": {"title": "Dynamic linker modified", "urgency": "critical"},
    "audit_config": {"title": "Audit configuration modified", "urgency": "critical"},
    "systemd_units": {"title": "systemd unit modified", "urgency": "normal"},
    "network_config": {"title": "Network configuration modified", "urgency": "normal"},
    "firewall": {"title": "Firewall configuration modified", "urgency": "critical"},
    "file_delete": {"title": "File deleted or renamed", "urgency": "low"},
    "perm_change": {"title": "Permissions modified", "urgency": "normal"},
    "ownership_change": {"title": "Ownership modified", "urgency": "normal"},
    "mount_activity": {"title": "Filesystem mount activity", "urgency": "normal"},
    "time_change": {"title": "System time modified", "urgency": "critical"},
    "hostname_change": {"title": "Hostname/domain modified", "urgency": "critical"},
    "access_denied": {"title": "Access denied", "urgency": "low"},
    "ssh_keys": {"title": "SSH key activity detected", "urgency": "critical"},
    "audit_log_tamper": {"title": "Audit logs modified", "urgency": "critical"},
    "auditd_tampering": {"title": "auditd tooling executed", "urgency": "normal"},
}

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO, format="[auditd-notify] %(levelname)s: %(message)s")
log = logging.getLogger("auditd-notify")

# ============================================================
# USERNAME
# ============================================================

try:
    USERNAME = subprocess.check_output(["id", "-nu", str(USER_ID)], text=True).strip()
except Exception as e:
    log.error("Failed resolving USER_ID=%s: %s", USER_ID, e)
    sys.exit(1)

# ============================================================
# EVENT CACHE
# ============================================================

class EventCache:
    def __init__(self, ttl=8):
        self.ttl = ttl
        self.cache = {}

    def seen(self, event_id, key):
        now = time.monotonic()
        cache_key = f"{event_id}:{key}"
        self.cleanup(now)
        if cache_key in self.cache:
            return True
        self.cache[cache_key] = now
        return False

    def cleanup(self, now=None):
        if now is None:
            now = time.monotonic()
        expired = [k for k, ts in self.cache.items() if now - ts > self.ttl]
        for k in expired:
            del self.cache[k]

event_cache = EventCache(ttl=8)

# ============================================================
# EVENT BUFFER
# ============================================================

EVENT_BUFFER = {}

# ============================================================
# REGEX
# ============================================================

FIELD_REGEX = re.compile(r'([a-zA-Z0-9_]+)=(".*?"|\S+)')
EVENT_REGEX = re.compile(r'audit\([0-9.]+:([0-9]+)\)')
KEY_REGEX = re.compile(r'key="([^"]+)"')

# ============================================================
# HELPERS
# ============================================================

def parse_fields(line):
    fields = {}
    for key, value in FIELD_REGEX.findall(line):
        value = value.strip('"')
        fields[key] = value
    return fields

def resolve_uid(uid):
    if uid is None:
        return "?"
    if uid == "4294967295":
        return "unset"
    try:
        return pwd.getpwuid(int(uid)).pw_name
    except Exception:
        return uid

def decode_proctitle(hex_string):
    if not hex_string:
        return None
    try:
        decoded = bytes.fromhex(hex_string)
        return decoded.replace(b"\x00", b" ").decode(errors="ignore").strip()
    except Exception:
        return None

def extract_execve(line, fields):
    if "type=EXECVE" not in line:
        return None
    argv = []
    for i in range(0, 64):
        key = f"a{i}"
        if key not in fields:
            break
        value = fields[key].strip('"')
        argv.append(value)
    return " ".join(argv) if argv else None

URGENCY_ICONS = {
    "critical": "🔴",
    "normal":   "🟡",
    "low":      "🔵",
}

def send_telegram(message, urgency="normal"):
    if not TELEGRAM_ENABLED:
        return
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        log.warning("Telegram enabled but no bot token set")
        return
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        log.warning("Telegram enabled but no chat ID set")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_notification": False
    }).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=5) as response:
            if response.getcode() != 200:
                log.warning("Telegram send failed: HTTP %s", response.getcode())
    except URLError as e:
        log.warning("Telegram send error: %s", e)


def notify(title, body, urgency="normal"):
    # Desktop notification
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = f"/run/user/{USER_ID}"
    env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{USER_ID}/bus"
    cmd = [
        "runuser", "-u", USERNAME, "--",
        "notify-send", "-a", "auditd", "-u", urgency,
        "-t", NOTIFY_TIMEOUT, title, body
    ]
    try:
        subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5, check=False)
    except Exception as e:
        log.warning("notify-send failed: %s", e)

    # Telegram notification
    if TELEGRAM_ENABLED:
        icon = URGENCY_ICONS.get(urgency, "⚪")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        safe_body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        telegram_msg = f"{icon} <b>{safe_title}</b>\n🕐 {timestamp}\n{safe_body}"
        send_telegram(telegram_msg, urgency=urgency)

# ============================================================
# EVENT PROCESSOR (unchanged)
# ============================================================

def process_event(event_id, lines):
    merged = "\n".join(lines)
    key_match = KEY_REGEX.search(merged)
    if not key_match:
        return
    key = key_match.group(1)
    if key not in RULES:
        return
    if event_cache.seen(event_id, key):
        return

    fields = {}
    for line in lines:
        fields.update(parse_fields(line))

    exe = fields.get("exe")
    comm = fields.get("comm")

    if exe in IGNORE_EXECUTABLES:
        return
    if comm in IGNORE_COMM:
        return

    auid = fields.get("auid")
    uid = fields.get("uid")
    tty = fields.get("tty")
    pid = fields.get("pid")

    process = decode_proctitle(fields.get("proctitle"))
    if not process:
        for line in lines:
            process = extract_execve(line, parse_fields(line))
            if process:
                break

    rule = RULES[key]
    title = f"auditd: {rule['title']}"
    body_lines = [f"Rule: {key}"]
    if auid:
        body_lines.append(f"User: {resolve_uid(auid)} ({auid})")
    if uid:
        body_lines.append(f"Effective: {resolve_uid(uid)} ({uid})")
    if exe:
        body_lines.append(f"Executable: {exe}")
    if comm:
        body_lines.append(f"Command: {comm}")
    if tty:
        body_lines.append(f"TTY: {tty}")
    if pid:
        body_lines.append(f"PID: {pid}")
    if process:
        body_lines.append(f"Process: {process}")

    body = "\n".join(body_lines)
    notify(title, body, urgency=rule["urgency"])
    log.info("event=%s key=%s process=%s", event_id, key, process)

# ============================================================
# MAIN LOOP (unchanged)
# ============================================================

def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            time.sleep(0.05)
            continue
        event_match = EVENT_REGEX.search(line)
        if not event_match:
            continue
        event_id = event_match.group(1)
        now = time.monotonic()
        if event_id not in EVENT_BUFFER:
            EVENT_BUFFER[event_id] = {"time": now, "lines": []}
        EVENT_BUFFER[event_id]["lines"].append(line)

        expired = []
        for eid, data in EVENT_BUFFER.items():
            if now - data["time"] >= EVENT_BUFFER_TIMEOUT:
                process_event(eid, data["lines"])
                expired.append(eid)
        for eid in expired:
            del EVENT_BUFFER[eid]

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass