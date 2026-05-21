#!/usr/bin/env python3

import subprocess
import os

USER_ID = 1000
USERNAME = subprocess.check_output(
    ["id", "-nu", str(USER_ID)],
    text=True
).strip()

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
