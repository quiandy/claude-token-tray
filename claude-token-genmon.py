#!/usr/bin/env python3
#
# claude-token-tray -- Xfce panel widget for Claude Code subscription usage.
# Copyright (C) 2026 Andrea Chiarini
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; see the GNU LGPL
# (COPYING.LESSER) and GNU GPL (COPYING) for details.
"""Genmon widget: Claude Code subscription usage (5-hour and weekly windows).

Anthropic meters subscription usage as a server-side *utilization percentage*
over two rolling windows -- a 5-hour window (anchored to your first message) and
a 7-day window. There is no fixed local "token budget" for a plan; the effective
allowance is dynamic (varies by model, caching, demand) and only the percentage
is meaningful.

The exact percentages are retrievable two ways, both used by Claude Code itself:

  * the `anthropic-ratelimit-unified-{five_hour,seven_day}-utilization` response
    headers returned on every API call, and
  * `GET /api/oauth/usage` (this script's source of truth), authenticated with
    the OAuth token Claude Code stores in ~/.claude/.credentials.json.

So we read the real numbers directly -- no token-summing, no budgets, no
calibration. If the API call fails (offline, or an expired token we can't
refresh), we fall back to the legacy transcript-based ESTIMATE so the panel
still shows something; that path is clearly marked "(est)".

Output is the XML understood by xfce4-genmon-plugin.
"""

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

CRED_FILE = Path.home() / ".claude" / ".credentials.json"
PROJECTS_DIR = Path.home() / ".claude" / "projects"
CACHE_DIR = Path.home() / ".cache" / "claude-token-tray"
EVENTS_CACHE = CACHE_DIR / "events.json"        # fallback transcript memo
USAGE_CACHE = CACHE_DIR / "usage.json"          # last good live result

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
HTTP_TIMEOUT = float(os.environ.get("CLAUDE_HTTP_TIMEOUT", "4"))
# Don't re-poll the API if the cached live result is younger than this; the
# panel refreshes every ~5s but utilization moves slowly (seconds).
LIVE_MIN_POLL = int(os.environ.get("CLAUDE_LIVE_MIN_POLL", "180"))
# How long a cached live result stays usable when a refresh fails (seconds).
LIVE_STALE_MAX = int(os.environ.get("CLAUDE_LIVE_STALE_SECONDS", "900"))

ICON = "✳"
HOUR = 3600
DAY = 86400

# After this many minutes without transcript writes, grey the label out.
IDLE_MINUTES = int(os.environ.get("CLAUDE_IDLE_MINUTES", "30"))

# --- fallback-estimate tunables (only used when the live API is unreachable) --
WINDOW_5H = int(os.environ.get("CLAUDE_5H_SECONDS", str(5 * HOUR)))
WINDOW_WEEK = int(os.environ.get("CLAUDE_WEEK_SECONDS", str(7 * DAY)))
BUDGET_5H = float(os.environ.get("CLAUDE_5H_BUDGET", "6000000"))
BUDGET_WEEK = float(os.environ.get("CLAUDE_WEEKLY_BUDGET", "60000000"))
W_INPUT = float(os.environ.get("CLAUDE_W_INPUT", "1"))
W_OUTPUT = float(os.environ.get("CLAUDE_W_OUTPUT", "5"))
W_CACHE_READ = float(os.environ.get("CLAUDE_W_CACHE_READ", "0.1"))
W_CACHE_WRITE = float(os.environ.get("CLAUDE_W_CACHE_WRITE", "1.25"))


# --------------------------------------------------------------------------- #
# Live usage (source of truth)                                                #
# --------------------------------------------------------------------------- #
def access_token():
    try:
        oauth = json.loads(CRED_FILE.read_text())["claudeAiOauth"]
    except (OSError, json.JSONDecodeError, KeyError):
        return None
    return oauth.get("accessToken")


def fetch_live_usage():
    """GET /api/oauth/usage. Returns one of:
      ("ok", data)               -- parsed usage dict
      ("backoff", retry_seconds) -- HTTP 429; respect Retry-After
      ("fail", None)             -- offline / auth / parse error
    The endpoint is itself rate-limited (429 with Retry-After ~3 min), so
    callers must not poll it eagerly."""
    token = access_token()
    if not token:
        return "fail", None
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            "User-Agent": "claude-token-tray",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return "ok", json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            try:
                retry = int(e.headers.get("Retry-After", "171"))
            except (TypeError, ValueError):
                retry = 171
            return "backoff", retry
        return "fail", None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return "fail", None


def read_state():
    """Persisted live state: {at, data, retry_until}."""
    try:
        return json.loads(USAGE_CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        USAGE_CACHE.write_text(json.dumps(state))
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Fallback estimate (transcript token sums) -- only when live is unreachable   #
# --------------------------------------------------------------------------- #
def iso_to_epoch(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def weighted(usage):
    return (
        usage.get("input_tokens", 0) * W_INPUT
        + usage.get("output_tokens", 0) * W_OUTPUT
        + usage.get("cache_read_input_tokens", 0) * W_CACHE_READ
        + usage.get("cache_creation_input_tokens", 0) * W_CACHE_WRITE
    )


def parse_events(path, horizon):
    events = []
    try:
        data = path.read_bytes()
    except OSError:
        return events
    for raw in data.split(b"\n"):
        if b'"usage"' not in raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        usage = (entry.get("message") or {}).get("usage") or {}
        if "output_tokens" not in usage and "input_tokens" not in usage:
            continue
        epoch = iso_to_epoch(entry.get("timestamp"))
        if epoch is None or epoch < horizon:
            continue
        events.append((epoch, weighted(usage)))
    return events


def collect_events(now):
    horizon = now - (WINDOW_WEEK + DAY)
    try:
        cache = json.loads(EVENTS_CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        cache = {}
    new_cache, events = {}, []
    for path in PROJECTS_DIR.glob("*/*.jsonl"):
        key = str(path)
        try:
            st = path.stat()
        except OSError:
            continue
        cached = cache.get(key)
        if cached and cached["mtime"] == st.st_mtime and cached["size"] == st.st_size:
            # Tolerate caches written by older versions (3-tuples) by keeping
            # only (epoch, weighted).
            ev = [(e[0], e[1]) for e in cached["events"]]
        else:
            ev = parse_events(path, horizon)
        ev = [e for e in ev if e[0] >= horizon]
        new_cache[key] = {"mtime": st.st_mtime, "size": st.st_size, "events": ev}
        events.extend(ev)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        EVENTS_CACHE.write_text(json.dumps(new_cache))
    except OSError:
        pass
    return events


def five_hour_anchor(events, now):
    anchor = None
    for ts, _ in sorted(events):
        if anchor is None or ts >= anchor + WINDOW_5H:
            anchor = ts
    if anchor is None or now >= anchor + WINDOW_5H:
        return None, None
    return anchor, anchor + WINDOW_5H


def estimate_usage(now):
    """Legacy approximation. Returns the same shape as the live API, with a
    synthesised resets_at for the 5h window (the weekly one is rolling)."""
    events = collect_events(now)
    if not events:
        return None
    anchor, reset5 = five_hour_anchor(events, now)
    used5 = sum(w for ts, w in events if anchor is not None and ts >= anchor)
    used7 = sum(w for ts, w in events if ts >= now - WINDOW_WEEK)
    out = {
        "five_hour": {
            "utilization": 100 * used5 / BUDGET_5H if BUDGET_5H else 0,
            "resets_at": datetime.fromtimestamp(reset5).astimezone().isoformat()
            if reset5 else None,
        },
        "seven_day": {
            "utilization": 100 * used7 / BUDGET_WEEK if BUDGET_WEEK else 0,
            "resets_at": None,
        },
    }
    return out


# --------------------------------------------------------------------------- #
# Rendering                                                                    #
# --------------------------------------------------------------------------- #
def colour(pct):
    if pct >= 90:
        return "#e06c75"
    if pct >= 70:
        return "#e5c07b"
    return None


def span(text, pct):
    c = colour(pct)
    return f"<span foreground='{c}'>{text}</span>" if c else text


def reset_hm(resets_at):
    epoch = iso_to_epoch(resets_at) if resets_at else None
    return datetime.fromtimestamp(epoch).strftime("%H:%M") if epoch else None


def newest_transcript_mtime():
    latest = 0.0
    for path in PROJECTS_DIR.glob("*/*.jsonl"):
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            pass
    return latest


def render(data, now, source, age=0.0):
    fh = data.get("five_hour") or {}
    sd = data.get("seven_day") or {}
    pct5 = float(fh.get("utilization") or 0)
    pct7 = float(sd.get("utilization") or 0)
    reset5 = reset_hm(fh.get("resets_at"))
    reset7 = reset_hm(sd.get("resets_at"))

    tag = " (est)" if source == "estimate" else ""
    label_5h = span(f"5h {pct5:.0f}%{tag}", pct5)
    label_7d = span(f"7d {pct7:.0f}%", pct7)
    parts = [ICON, label_5h, "·", label_7d]
    if reset5:
        parts += ["·", f"↻{reset5}"]
    label = " ".join(parts)

    idle = (now - newest_transcript_mtime()) > IDLE_MINUTES * 60
    if idle:
        print(f"<txt><span foreground='#888888'>{label}</span></txt>")
    else:
        print(f"<txt>{label}</txt>")

    if source == "live":
        src_line = "source: live  (GET /api/oauth/usage)"
    elif source == "cache":
        src_line = f"source: cached live ({int(age)}s old)"
    else:
        src_line = "source: ESTIMATE -- API unreachable; calibrate budgets"

    tip = [f"Claude usage{'  [idle]' if idle else ''}", "", src_line, ""]
    tip.append(f"5-hour window: {pct5:.0f}%")
    if reset5:
        tip.append(f"  resets at {reset5}")
    tip.append(f"7-day window:  {pct7:.0f}%")
    if reset7:
        tip.append(f"  resets at {reset7}")

    extra = (data.get("extra_usage") or {})
    if extra.get("is_enabled"):
        tip += ["", f"extra usage: {extra.get('utilization') or 0:.0f}% of "
                f"{extra.get('monthly_limit')} {extra.get('currency') or ''}".strip()]
    print("<tool>" + "\n".join(tip) + "</tool>")


def main():
    now = time.time()
    state = read_state()
    data, at = state.get("data"), state.get("at", 0)
    age = now - at

    # Serve a recent result without re-polling: either the cache is still fresh,
    # or the endpoint told us (via 429 Retry-After) not to call again yet. The
    # panel ticks every ~5s but /api/oauth/usage is itself rate-limited.
    if data and (age < LIVE_MIN_POLL or now < state.get("retry_until", 0)):
        render(data, now, "live")
        return

    status, payload = fetch_live_usage()
    if status == "ok":
        write_state({"at": now, "data": payload, "retry_until": 0})
        render(payload, now, "live")
        return
    if status == "backoff" and data:
        state["retry_until"] = now + payload
        write_state(state)
        # keep showing the last good numbers while backing off
        render(data, now, "live")
        return

    # Live unavailable -- show a still-usable older cache, then the estimate.
    if data and age < LIVE_STALE_MAX:
        render(data, now, "cache", age)
        return

    est = estimate_usage(now)
    if est is not None:
        render(est, now, "estimate")
        return

    print(f"<txt>{ICON} n/a</txt>")
    print("<tool>No live usage and no Claude Code transcripts found.</tool>")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the panel
        print(f"{ICON} err")
        print(f"<tool>{e}</tool>")
