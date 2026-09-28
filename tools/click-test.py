"""Headless-ish check: load the whale and synthesise a real click on her.

Reproduces the crash path (press -> release -> _play_tap -> sfx) without a human.
If this script prints the success line, clicking her no longer kills the process.

Run:  python tools/click-test.py
"""
from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

HERE = Path(__file__).resolve().parent
APP = HERE.parent / "whale-qt.pyw"


def load_whale():
    """Import whale-qt.pyw as a module (its `__name__` won't be __main__)."""
    spec = importlib.util.spec_from_file_location("whale_under_test", APP)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["whale_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mod = load_whale()
    app = QApplication([])
    w = mod.Whale()
    w.show()

    # click her body (below the bubble), the same spot a user would hit
    def do_click() -> None:
        pos = QPoint(w.width() // 2, int(w.height() * 0.78))
        print(f"clicking at {pos.x()},{pos.y()} ...", flush=True)
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos)

    def report() -> None:
        print("tap animation running:", w._tap_anim is not None
              and w._tap_anim.state() == mod.QPropertyAnimation.State.Running)
        print("squash value:", round(w._squash, 3))
        voices = getattr(w.sfx, "_voices", {})
        print("sfx voices:", sum(len(v) for v in voices.values()), "across", len(voices), "samples")

    QTimer.singleShot(2200, do_click)
    QTimer.singleShot(3000, do_click)      # second click: exercises replay
    QTimer.singleShot(6200, report)
    QTimer.singleShot(7000, app.quit)

    try:
        app.exec()
    except BaseException:
        traceback.print_exc()
        return 1
    print("OK — survived two clicks, no crash")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
