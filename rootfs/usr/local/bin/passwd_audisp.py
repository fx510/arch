#!/usr/bin/env python3

import sys
import subprocess
import time

USER_ID = 1000
COOLDOWN = 10  # seconds

USERNAME = subprocess.check_output(
    ["id", "-nu", str(USER_ID)],
    text=True
).strip()

last_alert = 0

for line in sys.stdin:

    if "shadow_read" not in line:
        continue

    now = time.time()

    if now - last_alert < COOLDOWN:
        continue

    last_alert = now

    cmd = [
        "runuser",
        "-u",
        USERNAME,
        "--",
        "env",
        f"XDG_RUNTIME_DIR=/run/user/{USER_ID}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{USER_ID}/bus",
        "WAYLAND_DISPLAY=wayland-1",
        "notify-send",
        "auditd alert",
        "/etc/shadow was read"
    ]

    subprocess.run(cmd)