
import os
import re
import sys
import pwd
import time
import logging
import subprocess

try:

    USERNAME = subprocess.check_output(
        ["id", "-nu", str(USER_ID)],
        text=True
    ).strip()

except Exception as e:

    # log.error("Failed resolving USER_ID=%s: %s", USER_ID, e)
    sys.exit(1)



def notify(title, body, urgency="normal"):
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = f"/run/user/{USER_ID}"
    env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{USER_ID}/bus"
    # Use sudo -u instead of runuser – better environment preservation
    cmd = [
        "sudo", "-u", USERNAME,
        "notify-send", "-a", "auditd", "-u", urgency,
        "-t", NOTIFY_TIMEOUT, title, body
    ]
    try:
        subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5, check=False)
    except Exception as e:
        pass
        # continue
        # log.warning("notify-send failed: %s", e)


notify('teast',"hi there")
