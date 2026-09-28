"""Hermes plugin for deepseek-whale — launches the floating pet with Hermes.

Loading this module IS the hook: Hermes imports every enabled plugin's
__init__.py during startup, which is the earliest reliable "Hermes is up" moment.

WHY wscript.exe AND NOT subprocess.Popen
----------------------------------------
The Hermes backend itself runs as python.exe and owns a console window. Anything
spawned from inside it inherits that console — closing the console killed the
pet along with the backend. Routing the launch through wscript.exe (the launcher
in start.vbs, window style 0) starts the pet outside this process tree — no
window, and nothing to inherit.

The pet also polls for Hermes.exe and quits when it goes away, so it never
outlives Hermes; double-launch is prevented on the pet's side via whale.lock.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VBS = HERE / "start.vbs"          # the launcher that detaches from our process tree
WHALE = HERE / "whale-qt.pyw"

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def launch() -> bool:
    """Start the pet detached from this process tree. True when a spawn was issued."""
    if not WHALE.exists():
        return False

    # Preferred: hand off to wscript so the pet leaves our process tree entirely.
    if VBS.exists():
        try:
            subprocess.Popen(
                ["wscript.exe", "//B", str(VBS)],
                creationflags=CREATE_NO_WINDOW,
                close_fds=True)
            return True
        except Exception:
            pass

    # Fallback: spawn directly. DETACHED_PROCESS rather than CREATE_NO_WINDOW —
    # the two flags are mutually exclusive — plus severed std handles so nothing
    # is inherited from the backend's console.
    exe = Path(sys.executable).with_name("pythonw.exe")
    if not exe.exists():
        exe = Path(sys.executable)
    try:
        subprocess.Popen(
            [str(exe), str(WHALE)],
            cwd=str(HERE),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=DETACHED_PROCESS,
            close_fds=True)
        return True
    except Exception:
        return False


# Runs at import time, i.e. when Hermes boots with this plugin enabled.
try:
    launch()
except Exception:
    pass          # a pet that fails to start must never break Hermes itself
