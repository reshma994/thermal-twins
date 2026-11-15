"""Launch the installed Microsoft Edge in new-headless mode and attach Playwright over CDP.

(Recent Edge builds no longer accept Playwright's legacy headless launch, so we start Edge ourselves.)
"""
from __future__ import annotations

import socket
import subprocess
import tempfile
import time

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def launch_edge(pw, port: int = 9333):
    profile = tempfile.mkdtemp(prefix="tt-edge-")
    proc = subprocess.Popen([EDGE, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                             "--no-first-run", "--disable-gpu", "--window-size=1440,900", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            break
        except OSError:
            time.sleep(0.25)
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    return browser, proc
