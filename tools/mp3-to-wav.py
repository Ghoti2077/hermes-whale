"""Convert the whale widget's mp3 samples to wav so QSoundEffect can play them.

QSoundEffect is the low-latency Qt player (right for click feedback) but it only
decodes PCM/wav. QMediaPlayer handles mp3, yet it rebuilds its pipeline on every
play, which is exactly the stutter we're getting rid of.

Writes next to the .pyw in sfx/ (the original assets stay untouched).
Run:  python tools/mp3-to-wav.py
"""
from __future__ import annotations

import wave
from pathlib import Path

import miniaudio

SRC = Path(r"D:\APP\herness\profiles\web\node_modules\dsh-whale-widget\assets")
OUT = Path(__file__).resolve().parents[1] / "sfx"
FILES = ["Ya1.mp3", "Ya2.mp3", "D1.mp3", "D2.mp3"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        src = SRC / name
        if not src.exists():
            print(f"  skip (missing): {name}")
            continue
        dec = miniaudio.decode_file(str(src))
        dst = OUT / (src.stem + ".wav")
        with wave.open(str(dst), "wb") as w:
            w.setnchannels(dec.nchannels)
            w.setsampwidth(2)                 # miniaudio gives signed 16-bit
            w.setframerate(dec.sample_rate)
            w.writeframes(dec.samples.tobytes())
        secs = len(dec.samples) / dec.nchannels / dec.sample_rate
        print(f"  {name} -> {dst.name}  {dec.nchannels}ch {dec.sample_rate}Hz {secs:.2f}s "
              f"({dst.stat().st_size} bytes)")
    print("done ->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
