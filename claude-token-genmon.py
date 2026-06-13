#!/usr/bin/env python3
"""Genmon widget: Claude Code usage across the 5-hour and weekly windows.

Anthropic meters subscription usage in two rolling windows: a 5-hour window
(anchored to your first message) and a 7-day window. The exact percentages
shown on claude.ai are computed server-side and are NOT stored locally, so we
approximate them from the per-message `usage` recorded in the transcripts under
~/.claude/projects, summed over each window and divided by a configurable
budget. See CALIBRATION below to make the percentages match claude.ai.

Output is the XML understood by xfce4-genmon-plugin.

CALIBRATION
-----------
The budgets are the only unknowns. To make a percentage match claude.ai:
  1. Hover the widget to read the window's weighted-token sum (e.g. 5h = 1.8M).
  2. Read the matching percentage on claude.ai (e.g. 5h = 30%).
  3. budget = sum / (percent/100)   ->   1.8M / 0.30 = 6.0M
  4. export CLAUDE_5H_BUDGET=6000000  (and likewise CLAUDE_WEEKLY_BUDGET)
Set these in the genmon command or your shell profile.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
CACHE_FILE = Path.home() / ".cache" / "claude-token-tray" / "events.json"

ICON = "✳"
HOUR = 3600
DAY = 86400
WINDOW_5H = int(os.environ.get("CLAUDE_5H_SECONDS", str(5 * HOUR)))
WINDOW_WEEK = int(os.environ.get("CLAUDE_WEEK_SECONDS", str(7 * DAY)))

# Budgets (in weighted "cost-equivalent" tokens) the percentages divide by.
# These are guesses for the Pro plan -- calibrate them (see module docstring).
BUDGET_5H = float(os.environ.get("CLAUDE_5H_BUDGET", "6000000"))
BUDGET_WEEK = float(os.environ.get("CLAUDE_WEEKLY_BUDGET", "60000000"))

# Per-token weights approximating relative cost (output and cache-write cost
# more than plain input; cache reads are cheap). Tunable via env.
W_INPUT = float(os.environ.get("CLAUDE_W_INPUT", "1"))
W_OUTPUT = float(os.environ.get("CLAUDE_W_OUTPUT", "5"))
W_CACHE_READ = float(os.environ.get("CLAUDE_W_CACHE_READ", "0.1"))
W_CACHE_WRITE = float(os.environ.get("CLAUDE_W_CACHE_WRITE", "1.25"))

# After this many minutes without transcript writes, grey the label out.
IDLE_MINUTES = int(os.environ.get("CLAUDE_IDLE_MINUTES", "30"))


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
    """Return [(epoch, weighted, raw_total)] for messages newer than horizon."""
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
        raw_total = (
            usage.get("input_tokens", 0)
            + usage.get("output_tokens", 0)
            + usage.get("cache_read_input_tokens", 0)
            + usage.get("cache_creation_input_tokens", 0)
        )
        events.append((epoch, weighted(usage), raw_total))
    return events


def collect_events(now):
    """Gather usage events from all transcripts, memoised by file mtime/size."""
    horizon = now - (WINDOW_WEEK + DAY)  # keep a day of slack past the week
    try:
        cache = json.loads(CACHE_FILE.read_text())
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
            ev = [tuple(e) for e in cached["events"]]
        else:
            ev = parse_events(path, horizon)
        ev = [e for e in ev if e[0] >= horizon]
        new_cache[key] = {"mtime": st.st_mtime, "size": st.st_size, "events": ev}
        events.extend(ev)

    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(new_cache))
    except OSError:
        pass
    return events


def five_hour_window(events, now):
    """Anchored 5h window: a new window starts on the first message >5h after
    the previous window's anchor. Returns (anchor, reset_epoch) or (None, None)
    if the most recent window has already elapsed."""
    anchor = None
    for ts, *_ in sorted(events):
        if anchor is None or ts >= anchor + WINDOW_5H:
            anchor = ts
    if anchor is None or now >= anchor + WINDOW_5H:
        return None, None
    return anchor, anchor + WINDOW_5H


def fmt(n):
    n = round(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def colour(pct):
    if pct >= 90:
        return "#e06c75"
    if pct >= 70:
        return "#e5c07b"
    return None


def span(text, pct):
    c = colour(pct)
    return f"<span foreground='{c}'>{text}</span>" if c else text


def main():
    now = time.time()
    events = collect_events(now)

    if not events:
        print(f"<txt>{ICON} n/a</txt>")
        print("<tool>No Claude Code usage found under ~/.claude/projects</tool>")
        return

    anchor, reset5 = five_hour_window(events, now)
    used5 = sum(w for ts, w, _ in events if anchor is not None and ts >= anchor)
    raw5 = sum(r for ts, _, r in events if anchor is not None and ts >= anchor)
    week_start = now - WINDOW_WEEK
    used7 = sum(w for ts, w, _ in events if ts >= week_start)
    raw7 = sum(r for ts, _, r in events if ts >= week_start)

    pct5 = 100 * used5 / BUDGET_5H if BUDGET_5H else 0
    pct7 = 100 * used7 / BUDGET_WEEK if BUDGET_WEEK else 0

    last_ts = max(ts for ts, _, _ in events)
    idle = (now - last_ts) > IDLE_MINUTES * 60

    label_5h = span(f"5h {pct5:.0f}%", pct5)
    label_7d = span(f"7d {pct7:.0f}%", pct7)
    if reset5 is not None:
        reset_str = datetime.fromtimestamp(reset5).strftime("%H:%M")
        label = f"{ICON} {label_5h} · {label_7d} · ↻{reset_str}"
    else:
        label = f"{ICON} {label_5h} · {label_7d}"

    if idle:
        print(f"<txt><span foreground='#888888'>{label}</span></txt>")
    else:
        print(f"<txt>{label}</txt>")

    if reset5 is not None:
        reset_full = datetime.fromtimestamp(reset5).strftime("%H:%M:%S")
        mins = int((reset5 - now) // 60)
        reset_line = f"5h window resets at {reset_full} (in {mins} min)"
    else:
        reset_line = "5h window inactive (resets on next message)"

    tip = [
        f"Claude usage  (Pro plan estimate){'  [idle]' if idle else ''}",
        "",
        f"5-hour window: {pct5:.0f}%  of {fmt(BUDGET_5H)} budget",
        f"  weighted: {fmt(used5)}   raw tokens: {raw5:,}",
        f"  {reset_line}",
        "",
        f"7-day window: {pct7:.0f}%  of {fmt(BUDGET_WEEK)} budget",
        f"  weighted: {fmt(used7)}   raw tokens: {raw7:,}",
        "",
        "Percentages are estimates -- calibrate budgets to match claude.ai:",
        "  budget = weighted_sum / (claude.ai_percent / 100)",
        "  export CLAUDE_5H_BUDGET=... CLAUDE_WEEKLY_BUDGET=...",
    ]
    print("<tool>" + "\n".join(tip) + "</tool>")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the panel
        print(f"{ICON} err")
        print(f"<tool>{e}</tool>")
