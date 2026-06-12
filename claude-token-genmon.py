#!/usr/bin/env python3
"""Genmon widget: show token usage of the most recent Claude Code session.

Finds the most recently modified transcript under ~/.claude/projects and
prints the context-window usage of its last assistant message in the XML
format understood by xfce4-genmon-plugin.
"""

import json
import os
import sys
import time
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
# Tokens currently in the context window, vs. the model's window size.
CONTEXT_LIMIT = int(os.environ.get("CLAUDE_CONTEXT_LIMIT", "200000"))
# After this many minutes without transcript writes the session counts as idle.
IDLE_MINUTES = int(os.environ.get("CLAUDE_IDLE_MINUTES", "30"))
ICON = "✳"  # ✳


def latest_transcript():
    files = PROJECTS_DIR.glob("*/*.jsonl")
    try:
        return max(files, key=lambda p: p.stat().st_mtime)
    except ValueError:
        return None


def last_usage(path, max_bytes=512 * 1024):
    """Scan the transcript backwards for the last assistant message with usage."""
    size = path.stat().st_size
    with open(path, "rb") as f:
        f.seek(max(0, size - max_bytes))
        lines = f.read().split(b"\n")
    for raw in reversed(lines):
        if b'"usage"' not in raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        msg = entry.get("message") or {}
        usage = msg.get("usage") or {}
        if "input_tokens" in usage:
            return entry, msg, usage
    return None, None, None


def fmt(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def main():
    path = latest_transcript()
    if path is None:
        print(f"<txt>{ICON} n/a</txt>")
        print("<tool>No Claude Code sessions found</tool>")
        return

    entry, msg, usage = last_usage(path)
    if usage is None:
        print(f"<txt>{ICON} …</txt>")
        print(f"<tool>No usage data yet in {path.name}</tool>")
        return

    ctx = (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )
    out = usage.get("output_tokens", 0)
    pct = min(100, round(100 * ctx / CONTEXT_LIMIT))
    idle = (time.time() - path.stat().st_mtime) > IDLE_MINUTES * 60

    label = f"{ICON} {fmt(ctx)}"
    if idle:
        print(f"<txt><span foreground='#888888'>{label}</span></txt>")
    else:
        print(f"<txt>{label}</txt>")

    tip = [
        f"Claude session: {path.stem[:8]}  ({path.parent.name.lstrip('-')})",
        f"Model: {msg.get('model', '?')}{'  [idle]' if idle else ''}",
        f"Context: {ctx:,} tokens ({pct}% of {fmt(CONTEXT_LIMIT)})",
        f"  input: {usage.get('input_tokens', 0):,}"
        f"  cache read: {usage.get('cache_read_input_tokens', 0):,}"
        f"  cache write: {usage.get('cache_creation_input_tokens', 0):,}",
        f"Last reply: {out:,} output tokens",
        f"Updated: {entry.get('timestamp', '?')}",
    ]
    print("<tool>" + "\n".join(tip) + "</tool>")
    print(f"<bar>{pct}</bar>")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the panel
        print(f"<txt>{ICON} err</txt>")
        print(f"<tool>{e}</tool>")
        sys.exit(0)
