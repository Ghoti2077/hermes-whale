"""DeepSeek Whale — PyQt6 floating pet.

Hand-feel ported from the DSH whale-widget:

  * drag that tracks the cursor exactly
  * four-edge snap on release (with a smooth glide, not a jump)
  * horizontal mirror flip while snapped left/right — TEXT FLIPS TOO
  * press-squash: the doll squashes while held, bottom edge stays put
  * idle breathing bob
  * fling with wall bounce and friction
  * right-click menu: refresh / flip / snap off / size / quit

Unlike the tkinter build (colour-key transparency) this uses WA_TranslucentBackground,
i.e. real per-pixel alpha.

Run without a console:  pythonw.exe whale-qt.pyw
"""
from __future__ import annotations

import faulthandler
import ctypes
import json
import math
import os
import subprocess
import threading
import time
import traceback
import urllib.request
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt,
                          QTimer, QUrl, pyqtProperty, pyqtSignal)
from PyQt6.QtGui import (QAction, QColor, QFont, QImage, QPainter, QPen, QPixmap,
                         QTransform)
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

# ------------------------------------------------------------------ config
FOLLOW_HERMES = True    # show only while the Hermes desktop app is running
HERMES_EXE = "Hermes.exe"
FOLLOW_POLL_S = 2       # how often to re-check Hermes (ctypes, so this is cheap)
CREATE_NO_WINDOW = 0x08000000   # keep tasklist from flashing a console
_ART_RAW = Path(r"D:\APP\herness\profiles\web\node_modules\dsh-whale-widget\assets\DSniang1.png")
ART = _ART_RAW
IMG_W = 220             # on-screen width of the art (and of the window)
ART_TOP = 0.42          # where the character starts; the bubble lives above it
SIZE_W = IMG_W
SIZE_H = int(IMG_W / (1.0 - ART_TOP))   # art fills the width, bubble above it
REFRESH_S = 60          # balance refresh interval
SNAP_MARGIN = 90        # release within this many px of an edge -> snap
SNAP_GAP = 0            # px kept between the whale and the snapped edge
CLICK_SLOP = 5          # px of movement still counted as a click, not a drag

# Bubble geometry, in window fractions. The big bubble sits high, then a chain of
# shrinking dots walks down to her head. The dots follow a quadratic Bézier
# (P0 = bubble bottom-left, P1 = bulge control, P2 = top of her head) — spacing
# them evenly on a straight line, as the first version did, reads as a rigid
# diagonal instead of a curve.
BUBBLE_BOX = (0.10, 0.055, 0.80, 0.30)
BUBBLE_DOTS = (
    (0.235, 0.355, 0.092),   # t=0.00 — leaves the bubble's lower-left
    (0.145, 0.435, 0.062),   # t=0.50 — bulges LEFT, so it starts off diagonal
    (0.115, 0.525, 0.040),   # t=1.00 — and settles almost straight down
)
ART_TOP = 0.42          # where the character starts; the bubble lives above it
BALANCE_FONT_PX = 21    # the balance readout
SPENT_HOLD_S = 1.5      # after a click, show today's spend for this many seconds
INSET = 0.94            # draw content scaled to this share, so the tap-squash
                        # (which grows vertically) never clips at the window top
FLING_FRICTION = 0.94
FLING_BOUNCE = 0.60
FLING_MIN = 2.0         # px/frame below which the fling stops
FRAME_MS = 16
BREATH_PX = 0           # 0 = no idle bob; the whale rests perfectly still
BREATH_SPEED = 0.05


# ------------------------------------------------------------------ data
def hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME")
    return Path(env) if env else Path.home() / "AppData" / "Local" / "hermes"


def api_key() -> str:
    k = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if k:
        return k
    f = hermes_home() / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def fetch_balance() -> dict:
    key = api_key()
    if not key:
        return {"error": "未配置 key"}
    req = urllib.request.Request(
        "https://api.deepseek.com/user/balance",
        headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
    except Exception as e:
        return {"error": type(e).__name__}
    info = (d.get("balance_infos") or [{}])[0]
    try:
        total = float(info.get("total_balance") or 0)
        return {"total": total,
                "granted": float(info.get("granted_balance") or 0),
                "topped_up": float(info.get("topped_up_balance") or 0),
                **_record_observation(total)}
    except Exception:
        return {"error": "解析失败"}


# ------------------------------------------------------------------ sound
# The mp3 originals are converted to wav by tools/mp3-to-wav.py so EVERY sound
# can go through QSoundEffect. QMediaPlayer decodes mp3 but rebuilds its pipeline
# on each play — that rebuild is the stutter heard on repeated clicks.
SFX_DIR = Path(__file__).resolve().parent / "sfx"
ASSETS = ART.parent          # the shipped exp-orb wav lives with the art
SFX_VOLUME = 0.8        # 0..1

# event -> file. Back to the widget's own paired cues: she asked for these by
# name, and the two-part press/release reads better than one long chime.
SFX = {
    "press": "Ya1.wav",       # 0.24s
    "release": "Ya2.wav",     # 0.11s
    "task": "minecraft-exp-orb.wav",
}
VOICES_PER_SAMPLE = 4   # rapid clicks overlap; one instance restarts and stutters


def _find_sfx(name: str) -> Path | None:
    for base in (SFX_DIR, ASSETS):
        p = base / name
        if p.exists():
            return p
    return None


class Sfx:
    """Click feedback via QSoundEffect, two voices per sample.

    winsound.PlaySound crashed the process outright (no Python traceback, so the
    fault was inside the C call). QSoundEffect is safe, but restarting a source
    that is already playing is what stuttered on rapid clicks — so each sample
    gets TWO instances and they alternate, letting a new click sound while the
    previous one is still finishing.
    """

    def __init__(self, volume: float = SFX_VOLUME) -> None:
        self.volume = volume
        self._voices: dict[str, list[QSoundEffect]] = {}
        self._slot: dict[str, int] = {}
        self._warm()

    def _voices_for(self, name: str) -> list[QSoundEffect]:
        vs = self._voices.get(name)
        if vs is not None:
            return vs
        path = _find_sfx(name)
        if path is None:
            return []
        vs = []
        for _ in range(VOICES_PER_SAMPLE):
            e = QSoundEffect()
            e.setSource(QUrl.fromLocalFile(str(path)))
            e.setVolume(self.volume)
            vs.append(e)
        self._voices[name] = vs
        self._slot[name] = 0
        return vs

    def _warm(self) -> None:
        """Decode every sample once now, so the first click isn't the slow one."""
        for name in SFX.values():
            for e in self._voices_for(name):
                e.setVolume(0.0)
                e.play()                 # forces the decoder to spin up
                e.setVolume(self.volume)

    def play(self, key: str) -> None:
        name = SFX.get(key)
        if not name:
            return
        vs = self._voices_for(name)
        if not vs:
            return
        i = self._slot.get(name, 0)
        vs[i].play()
        self._slot[name] = (i + 1) % len(vs)   # rotate voices so clicks never cut each other off


# ------------------------------------------------------------------ ledger
# Same accounting rule as dashboard/plugin_api.py: a DROP in balance counts as
# spend, a RISE is a top-up (tracked separately so it never cancels observed
# spend), and the first reading of a day is the baseline rather than spending.
# DeepSeek exposes no "today's usage" endpoint, so this is the only way to know.
LEDGER = Path(__file__).resolve().parent / "usage.json"
KEEP_DAYS = 90


def _load_ledger() -> dict:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_ledger(led: dict) -> None:
    try:
        LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass          # a read-only folder must not break the display


def _record_observation(total: float) -> dict:
    """Fold one balance reading into today's ledger."""
    today = time.strftime("%Y-%m-%d")
    led = _load_ledger()
    day = led.get(today) or {"since": None, "spent": 0.0, "topup": 0.0, "last": None}

    if day["last"] is None:
        day["since"] = total          # first reading = baseline, no spend inferred
    else:
        delta = day["last"] - total
        if delta > 0:                 # balance dropped -> spend
            day["spent"] = round(day["spent"] + delta, 8)
        elif delta < 0:               # balance rose -> top-up / grant
            day["topup"] = round(day["topup"] - delta, 8)
    day["last"] = total

    led[today] = day
    for stale in sorted(led)[:-KEEP_DAYS]:
        led.pop(stale, None)
    _save_ledger(led)
    return {"today_spent": day["spent"], "today_topup": day["topup"]}


def yuan(v: float) -> str:
    return f"¥{v:.2f}"


LOCK = Path(__file__).resolve().parent / "whale.lock"


def already_running() -> bool:
    """True when another live instance of this pet holds the lock.

    A pid file rather than a process-name scan: the Hermes plugin launches the pet
    blindly, so this is what keeps a second whale from stacking on top.
    """
    try:
        pid = int(LOCK.read_text(encoding="utf-8").strip())
    except Exception:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/fi", f"pid eq {pid}", "/nh"],
            capture_output=True, text=True, timeout=5,
            creationflags=CREATE_NO_WINDOW)
        return str(pid) in out.stdout
    except Exception:
        return False


def take_lock() -> None:
    try:
        LOCK.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def hermes_running() -> bool:
    """True while a VISIBLE top-level window owned by Hermes.exe exists.

    Checking for the process is useless: closing the Hermes window leaves all five
    Electron processes — and its Python backend — alive (it just hides). A pet
    watching for Hermes.exe therefore never notices the app was closed. "Open"
    in the user's sense means a visible window, so that is what we test.

    EnumWindows over ctypes rather than spawning tasklist/powershell: this runs
    every couple of seconds, and a subprocess per poll is both slower and nosier.
    """
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        target = HERMES_EXE.lower()

        def cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            # Size filtering must be skipped while minimised: GetWindowRect reports
            # an empty rect (0x0 or -32000) for a minimised window, so the main
            # window would fail the "big enough" test and the pet would quit every
            # time Hermes was minimised. Minimised is still OPEN — only a hidden
            # window (IsWindowVisible False) means the user closed it.
            if not user32.IsIconic(hwnd):
                r = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                if (r.right - r.left) < 300 or (r.bottom - r.top) < 200:
                    return True      # helper / tray windows are tiny — skip them
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value:
                return True
            h = kernel32.OpenProcess(0x1000, False, pid.value)   # QUERY_LIMITED_INFORMATION
            if not h:
                return True
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    if buf.value.lower().endswith("\\" + target):
                        cb.hit = True
                        return False
            finally:
                kernel32.CloseHandle(h)
            return True

        cb.hit = False
        user32.EnumWindows(
            ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
        return bool(cb.hit)
    except Exception:
        return True          # fail open: never strand the pet because a probe broke


# ------------------------------------------------------------------ window
class Whale(QWidget):
    # Emitted from the worker thread; Qt queues it onto the GUI thread for us.
    balance_ready = pyqtSignal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("DeepSeek Whale")
        self.resize(SIZE_W, SIZE_H)
        self._scale = 1.0

        src = QPixmap(str(ART))
        if src.isNull():
            raise SystemExit(f"找不到素材: {ART}")
        # Hard-threshold alpha AFTER scaling: smooth scaling leaves faint
        # semi-transparent pixels just outside the art, and against the desktop
        # they read as a thin pale outline.
        img = src.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        img = img.scaled(IMG_W, IMG_W, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        for yy in range(img.height()):
            for xx in range(img.width()):
                c = img.pixelColor(xx, yy)
                c.setAlpha(255 if c.alpha() >= 128 else 0)
                img.setPixelColor(xx, yy, c)
        self.base = QPixmap.fromImage(img)
        self.flipped = self.base.transformed(QTransform().scale(-1.0, 1.0))
        self._art_img = img          # kept for hit-testing (alpha lookup)

        self.bal: dict | None = None
        self.breath = 0.0
        self._squash = 1.0
        self.mirror = False
        self.snap_on = True

        self.vx = self.vy = 0.0
        self.flying = False
        self.sfx = Sfx()
        self.balance_ready.connect(self._apply_balance)
        self._fetching = False
        self._grab: QPoint | None = None
        self._win0 = QPoint()
        self._press_pos = QPoint()
        self._samples: list[tuple[float, int, int]] = []
        self._anim: QPropertyAnimation | None = None
        self._tap_anim: QPropertyAnimation | None = None
        self._edges: tuple[int, int] | None = None
        self._follow_ticks = 0
        self._hidden = False
        self._show_spent = False            # bubble currently showing today's spend
        self._spent_timer: QTimer | None = None
        self.today_spent: float | None = None

        # park bottom-right of the available area
        geo = QApplication.primaryScreen().availableGeometry()
        self.move(geo.right() - self.width() - SNAP_GAP,
                  geo.bottom() - self.height() - SNAP_GAP)

        self._refresh()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)   # default drifts ~15ms
        self._timer.timeout.connect(self._frame)
        self._timer.start(FRAME_MS)

    # ------------------------------------------------- squash (animatable)
    def _get_squash(self) -> float:
        return self._squash

    def _set_squash(self, v: float) -> None:
        self._squash = v
        self.update()

    squash = pyqtProperty(float, fget=_get_squash, fset=_set_squash)

    # ------------------------------------------------- paint
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W, H = self.width(), self.height()

        # The press-squash scales EVERYTHING about the content centre. INSET only
        # kicks in while the vertical axis is GROWING (sy > 1) — applying it at
        # rest too was what left a 6% gap on every side and made her look
        # misaligned with the screen edges.
        sy = 2.0 - self._squash
        inset = INSET if sy > 1.0 else 1.0
        p.save()
        p.translate(W / 2.0, H * 0.58)
        p.scale(self._squash * inset, sy * inset)
        p.translate(-W / 2.0, -H * 0.58)

        mid = int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)

        # --- dot trail first, so the big bubble overlaps its neck
        p.setPen(QPen(QColor("#2b3a55"), 2.2))
        p.setBrush(QColor("#fcfcfd"))
        for fx, fy, fs in BUBBLE_DOTS:
            if self.mirror:
                fx = 1.0 - fx - fs
            s = W * fs
            p.drawEllipse(QRectF(W * fx, H * fy, s, s))

        bx, by, bw, bh = BUBBLE_BOX
        if self.mirror:
            bx = 1.0 - bx - bw
        box = QRectF(W * bx, H * by, W * bw, H * bh)
        p.setPen(QPen(QColor("#2b3a55"), 2.4))
        p.setBrush(QColor("#fcfcfd"))
        p.drawEllipse(box)

        has_bal = bool(self.bal and "total" in self.bal)
        if self._show_spent and self.today_spent is not None:
            main = f"今日 {yuan(self.today_spent)}"      # click-to-peek
        elif has_bal:
            main = yuan(self.bal["total"])
        elif self.bal and "error" in self.bal:
            main = self.bal["error"]
        else:
            main = "…" if self.bal is None else "—"

        # one centred line — the old "点击刷新" hint is gone
        p.setPen(QColor("#2b3a55"))
        p.setFont(QFont("Microsoft YaHei UI", BALANCE_FONT_PX, QFont.Weight.Bold))
        p.drawText(box, mid, main)

        # --- the character: fills the window width, sits below the bubble
        img_w = W
        art_y = int(H * ART_TOP)
        pm = self.flipped if self.mirror else self.base
        p.drawPixmap(0, art_y, img_w, img_w, pm)

        p.restore()

    # ------------------------------------------------- mouse
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.flying = False
            self._grab = e.globalPosition().toPoint()
            self._press_pos = e.position().toPoint()
            self._win0 = self.pos()
            self._samples = []
            # Deliberately no press animation: the whole tap animation plays on
            # release, so a quick tap and a slow press feel identical.

    def mouseMoveEvent(self, e) -> None:
        if self._grab is None:
            return
        gp = e.globalPosition().toPoint()
        self.move(self._win0 + (gp - self._grab))

        now = time.time()
        self._samples.append((now, gp.x(), gp.y()))
        self._samples = [s for s in self._samples if now - s[0] < 0.15][-6:]

        # Turn on SUSTAINED direction, not on distance from where the drag started.
        # A shaky hand reverses every sample or two; requiring three consecutive
        # same-way steps means she only turns when the motion is real — and turns
        # immediately, because no distance threshold has to be crossed first.
        recent = self._samples[-4:]
        if len(recent) >= 3:
            steps = [recent[i + 1][1] - recent[i][1] for i in range(len(recent) - 1)]
            if all(s <= 0 for s in steps) and any(s < 0 for s in steps):
                self.mirror = True      # pulling her left → she faces right
            elif all(s >= 0 for s in steps) and any(s > 0 for s in steps):
                self.mirror = False
        # No update() here: Qt already repaints the widget on move(), and a full
        # repaint per mouse event is what made dragging feel choppy.

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton or self._grab is None:
            return
        gp = e.globalPosition().toPoint()
        moved = (gp - self._grab).manhattanLength() if self._grab else 0
        self._grab = None

        # A tap on the whale herself = one fixed-length animation + both sounds,
        # no matter how long the press lasted.
        if moved <= CLICK_SLOP and self._hit_art(self._press_pos):
            self._play_tap()
            self._refresh()
            return

        self._squash_to(1.0)           # a real drag just settles back

        # fling if it was moving fast enough
        if len(self._samples) >= 2:
            (t0, x0, y0), (t1, x1, y1) = self._samples[0], self._samples[-1]
            dt = t1 - t0
            if dt > 0:
                self.vx = (x1 - x0) / dt * (FRAME_MS / 1000.0)
                self.vy = (y1 - y0) / dt * (FRAME_MS / 1000.0)
        self._samples = []
        if abs(self.vx) > 2.5 or abs(self.vy) > 2.5:
            self.flying = True
        elif self.snap_on:
            self._snap()

    def contextMenuEvent(self, e) -> None:
        m = QMenu(self)
        act_refresh = QAction("刷新余额", self)
        act_refresh.triggered.connect(self._refresh)
        act_flip = QAction("手动翻转", self)
        act_flip.triggered.connect(self._toggle_mirror)
        act_snap = QAction("吸附", self)
        act_snap.setCheckable(True)
        act_snap.setChecked(self.snap_on)
        act_snap.triggered.connect(lambda v: setattr(self, "snap_on", v))
        m.addAction(act_refresh)
        m.addAction(act_flip)
        m.addAction(act_snap)
        m.addSeparator()
        for label, size in (("小 160", 160), ("中 220", 220), ("大 300", 300)):
            a = QAction(label, self)
            a.triggered.connect(lambda _c=False, s=size: self._resize_to(s))
            m.addAction(a)
        m.addSeparator()
        a_quit = QAction("退出", self)
        a_quit.triggered.connect(QApplication.quit)
        m.addAction(a_quit)
        m.exec(e.globalPos())

    # ------------------------------------------------- helpers
    def _art_edges(self) -> tuple[int, int]:
        """(left, right) in window coords of the art's opaque bounds, cached.

        The art carries a transparent margin, so aligning the WINDOW edge to the
        screen leaves a visible gap beside her. Snap to the pixels instead.
        """
        if self._edges is None:
            img = self._art_img
            w, h = img.width(), img.height()
            left, right = 0, w
            for x in range(w):
                if any(img.pixelColor(x, y).alpha() > 40 for y in range(0, h, 3)):
                    left = x
                    break
            for x in range(w - 1, -1, -1):
                if any(img.pixelColor(x, y).alpha() > 40 for y in range(0, h, 3)):
                    right = x + 1
                    break
            self._edges = (left, right)
        lx, rx = self._edges
        scale = self.width() / self._art_img.width()
        return int(lx * scale), int(rx * scale)

    def _hit_art(self, pos: QPoint) -> bool:
        """True when the point sits on an opaque pixel of the character."""
        W, H = self.width(), self.height()
        art_y = int(H * ART_TOP)
        if not (0 <= pos.x() < W and art_y <= pos.y() < art_y + W):
            return False
        img = self._art_img
        sx = int(pos.x() * img.width() / W)
        sy = int((pos.y() - art_y) * img.height() / W)
        if self.mirror:
            sx = img.width() - 1 - sx
        return img.pixelColor(sx, sy).alpha() > 40

    def _play_tap(self) -> None:
        """One tap animation + sound, restarted from scratch on every click.

        Deliberately NOT guarded against a running animation: clicking fast should
        make her squash again immediately, in step with each click, rather than
        swallowing the input until the previous animation finishes.
        """
        self.sfx.play("press")
        if self._tap_anim is not None:
            self._tap_anim.stop()
        a = QPropertyAnimation(self, b"squash", self)
        a.setDuration(560)              # longer and gentler reads smoother
        a.setKeyValueAt(0.0, self._squash)   # start from wherever we are now
        a.setKeyValueAt(0.26, 0.88)     # squash in
        a.setKeyValueAt(0.58, 1.05)     # small overshoot
        a.setKeyValueAt(1.0, 1.0)       # settle
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start()
        self._tap_anim = a
        # Ya1 runs 0.24s, so firing Ya2 at 146ms buried it inside the first sample
        # and the pair read as one sound. Wait for Ya1 to finish instead.
        QTimer.singleShot(250, lambda: self.sfx.play("release"))

        # Swap the bubble to today's spend for SPENT_HOLD_S seconds, then let it
        # fall back to the balance on its own.
        self._show_spent = True
        if self._spent_timer is not None:
            self._spent_timer.stop()
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(self._end_spent_peek)
        t.start(int(SPENT_HOLD_S * 1000))
        self._spent_timer = t
        self.update()

    def _end_spent_peek(self) -> None:
        self._show_spent = False
        self.update()

    def _squash_to(self, target: float) -> None:
        if self._anim:
            self._anim.stop()
        a = QPropertyAnimation(self, b"squash", self)
        a.setDuration(120 if target < 1.0 else 220)
        a.setStartValue(self._squash)
        a.setEndValue(target)
        a.setEasingCurve(QEasingCurve.Type.OutBack if target > 1.0
                         else QEasingCurve.Type.OutQuad)
        a.start()
        self._anim = a

    def _toggle_mirror(self) -> None:
        self.mirror = not self.mirror
        self.update()

    def _resize_to(self, img_w: int) -> None:
        """Resize by art width; the window keeps the bubble zone above it."""
        self._scale = img_w / IMG_W
        self.resize(int(SIZE_W * self._scale), int(SIZE_H * self._scale))
        self.update()

    def _snap(self) -> None:
        """Glide to the nearest edge; mirror when parking left or right."""
        geo = QApplication.primaryScreen().availableGeometry()
        x, y, w, h = self.x(), self.y(), self.width(), self.height()

        d_left, d_right = x - geo.left(), geo.right() - (x + w)
        d_top, d_bottom = y - geo.top(), geo.bottom() - (y + h)
        nearest = min(d_left, d_right, d_top, d_bottom)
        if nearest > SNAP_MARGIN:
            return

        tx, ty = x, y
        left_pad, right_pad = self._art_edges()
        if nearest == d_left:
            # line her actual opaque edge up with the screen edge, not the window's
            tx, self.mirror = geo.left() + SNAP_GAP - left_pad, True
        elif nearest == d_right:
            tx, self.mirror = geo.right() - w - SNAP_GAP + (w - right_pad), False
        elif nearest == d_top:
            ty = geo.top() + SNAP_GAP
        else:
            ty = geo.bottom() - h - SNAP_GAP

        a = QPropertyAnimation(self, b"pos", self)
        a.setDuration(180)
        a.setStartValue(self.pos())
        a.setEndValue(QPoint(tx, ty))
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.start()
        self._anim = a
        self.update()

    def _refresh(self) -> None:
        """Fetch on a worker thread.

        The HTTP call used to run on the GUI thread, so a click during a slow
        request froze the animation — that was the "click fast and it stutters"
        symptom, not the audio.
        """
        if self._fetching:
            return
        self._fetching = True

        def work() -> None:
            out = fetch_balance()
            try:
                self.balance_ready.emit(out)   # queued onto the GUI thread
            except RuntimeError:
                pass        # widget already destroyed (the app is shutting down)

        threading.Thread(target=work, daemon=True).start()

    def _apply_balance(self, out: dict) -> None:
        self._fetching = False
        was = self.bal
        self.bal = out
        if "today_spent" in out:
            self.today_spent = out["today_spent"]
        # exp-orb when the number actually moved (the widget's "task finished" cue)
        if "total" in out and (was is None or was.get("total") != out["total"]):
            self.sfx.play("task")
        self.update()
        QTimer.singleShot(REFRESH_S * 1000, self._refresh)

    # ------------------------------------------------- frame loop
    def _frame(self) -> None:
        geo = QApplication.primaryScreen().availableGeometry()
        if self.flying:
            x = self.x() + int(round(self.vx))
            y = self.y() + int(round(self.vy))
            if x < geo.left():
                x, self.vx = geo.left(), -self.vx * FLING_BOUNCE
            elif x + self.width() > geo.right():
                x, self.vx = geo.right() - self.width(), -self.vx * FLING_BOUNCE
            if y < geo.top():
                y, self.vy = geo.top(), -self.vy * FLING_BOUNCE
            elif y + self.height() > geo.bottom():
                y, self.vy = geo.bottom() - self.height(), -self.vy * FLING_BOUNCE
            self.vx *= FLING_FRICTION
            self.vy *= FLING_FRICTION
            self.move(int(x), int(y))
            if abs(self.vx) < FLING_MIN and abs(self.vy) < FLING_MIN:
                self.flying = False
                self.vx = self.vy = 0.0
                if self.snap_on:
                    self._snap()
        elif BREATH_PX:
            self.breath = math.sin(self._phase()) * BREATH_PX
            self.update()
        else:
            self.breath = 0.0       # idle: nothing to repaint

        # Follow Hermes: hidden while it's closed, back when it returns. Polled
        # every FOLLOW_POLL_S seconds, not every frame (tasklist is a subprocess).
        if FOLLOW_HERMES:
            self._follow_ticks += 1
            if self._follow_ticks * FRAME_MS >= FOLLOW_POLL_S * 1000:
                self._follow_ticks = 0
                alive = hermes_running()
                if alive and self._hidden:
                    self.show()
                    self._hidden = False
                elif not alive and not self._hidden:
                    # Quit outright rather than hide: a hidden process still holds
                    # ~30MB of Qt state, and she asked for it to not linger.
                    QApplication.quit()
                    return

    def _phase(self) -> float:
        self._p = getattr(self, "_p", 0.0) + BREATH_SPEED
        return self._p


def main() -> None:
    # A pythonw process has no console, so any stray exception vanishes silently
    # and the pet just disappears. Log crashes + dump on hard faults so the next
    # failure leaves evidence instead of nothing.
    log_path = Path(__file__).resolve().parent / "whale-error.log"
    # Cap the log: it is append-only across runs, and a crash loop would otherwise
    # grow it without bound.
    try:
        if log_path.exists() and log_path.stat().st_size > 1_000_000:
            log_path.write_text("", encoding="utf-8")
    except Exception:
        pass
    log = open(log_path, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=log)
    log.write(f"\n--- start {time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} ---\n")

    # The Hermes plugin spawns us on boot without checking; refuse to stack.
    if already_running():
        log.write("--- another instance is alive, exiting ---\n")
        log.flush()
        return
    take_lock()

    try:
        app = QApplication([])
        app.setQuitOnLastWindowClosed(True)
        w = Whale()
        w.show()
        app.exec()
    except BaseException:
        traceback.print_exc(file=log)
        log.flush()
        raise
    finally:
        log.write("--- exit ---\n")
        log.flush()
        # Drop the lock on the way out so a stale pid can never masquerade as a
        # live instance later (pids get reused).
        try:
            LOCK.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
