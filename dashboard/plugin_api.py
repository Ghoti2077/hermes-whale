"""DeepSeek balance + local spend ledger, mounted at /api/plugins/deepseek-whale/.

- Reads DEEPSEEK_API_KEY from the env or <HERMES_HOME>/.env (key never leaves here).
- Calls GET https://api.deepseek.com/user/balance.
- Keeps a per-day ledger in usage.json next to this plugin: a *drop* in balance is
  the account-observed spend; a *rise* is a top-up, recorded separately so it never
  cancels out already-observed spend. The first reading of a day is the baseline.

Self-check: python plugin_api.py
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

_TTL = 60  # seconds
_CACHE: dict = {"at": 0.0, "data": None}
_API = "https://api.deepseek.com/user/balance"
_LEDGER = Path(__file__).resolve().parents[1] / "usage.json"
_KEEP_DAYS = 90


def _hermes_home() -> Path:
    """Profile-safe home: $HERMES_HOME, else climb out of plugins/<id>/dashboard/."""
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3]


def _api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    p = _hermes_home() / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _load_ledger() -> dict:
    try:
        return json.loads(_LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_ledger(led: dict) -> None:
    try:
        _LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass  # a read-only plugin dir must not break the balance display


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
        elif delta < 0:               # balance rose -> top-up / grant, kept apart
            day["topup"] = round(day["topup"] - delta, 8)
    day["last"] = total

    led[today] = day
    for stale in sorted(led)[:-_KEEP_DAYS]:
        led.pop(stale, None)
    _save_ledger(led)
    return {"today_spent": day["spent"], "today_topup": day["topup"],
            "today_since_balance": day["since"]}


def _fetch() -> dict:
    key = _api_key()
    if not key:
        return {"ok": False, "error": "no_key",
                "detail": "未找到 DEEPSEEK_API_KEY（.env 或环境变量）"}
    req = urllib.request.Request(_API, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.load(r)
    except Exception as e:  # network / 401 / parse — surface, never crash the UI
        return {"ok": False, "error": type(e).__name__, "detail": str(e)[:200]}

    info = (d.get("balance_infos") or [{}])[0]
    total = float(info.get("total_balance") or 0)
    return {
        "ok": True,
        "available": bool(d.get("is_available")),
        "currency": info.get("currency", "CNY"),
        "total": info.get("total_balance", "0"),
        "granted": info.get("granted_balance", "0"),
        "topped_up": info.get("topped_up_balance", "0"),
        "at": int(time.time()),
        **_record_observation(total),
    }


@router.get("/balance")
def balance() -> dict:
    """Balance + today's observed spend (cached _TTL seconds)."""
    now = time.time()
    if _CACHE["data"] and now - _CACHE["at"] < _TTL:
        return _CACHE["data"]
    out = _fetch()
    # cache only successes — a transient failure shouldn't stick for a minute
    if out.get("ok"):
        _CACHE.update({"at": now, "data": out})
    return out


@router.get("/usage")
def usage() -> dict:
    """Ledger only — today plus the last few days, no network call."""
    led = _load_ledger()
    days = sorted(led)[-7:]
    return {
        "ok": True,
        "today": time.strftime("%Y-%m-%d"),
        "days": [{"date": d, **led[d]} for d in days],
    }


if __name__ == "__main__":
    # runnable self-check: python plugin_api.py
    print("hermes home:", _hermes_home())
    print("ledger file:", _LEDGER)
    print("key present:", bool(_api_key()))
    print(json.dumps(balance(), ensure_ascii=False, indent=2))
