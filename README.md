# claude-token-tray

Xfce panel (genmon) widget showing Claude Code usage across the **5-hour** and
**weekly** windows.

The panel shows something like:

```
✳ 5h 60% · 7d 86% · ↻14:58
```

- `5h 60%` — estimated usage of the current 5-hour window
- `7d 86%` — estimated usage of the rolling 7-day window (turns amber ≥70%,
  red ≥90%)
- `↻14:58` — when the current 5-hour window resets (omitted when no window is
  active)

The label greys out when no session has written for 30 minutes. Hover for the
weighted/raw token sums, exact reset time, and calibration hints.

## How it works

Anthropic meters subscription usage in a 5-hour window (anchored to your first
message) and a 7-day window. **The exact percentages shown on claude.ai are
computed server-side and are not stored locally**, so `claude-token-genmon.py`
approximates them: it sums the per-message `usage` recorded in
`~/.claude/projects/*/*.jsonl` over each window and divides by a configurable
budget.

Tokens are counted with cost-style weights (output and cache-writes weighted
up, cache-reads down) as a proxy for what claude.ai meters. Parsed events are
memoised in `~/.cache/claude-token-tray/` keyed by file mtime/size, so each
5-second refresh only re-reads transcripts that changed.

## Install

```sh
sudo apt install xfce4-genmon-plugin
./setup-panel.sh
```

`setup-panel.sh` registers a new genmon instance on the first panel (next to
the status icons) refreshing every 5 seconds.

> Note: the genmon font must be set to a real font (the setup uses `Sans 11`).
> A `Font=(none)` value renders the label invisibly while still drawing widgets.

## Calibration (make the percentages match claude.ai)

The budgets are the only unknowns. To calibrate a window once:

1. Hover the widget to read the window's weighted-token sum (e.g. `5h = 3.6M`).
2. Read the matching percentage on claude.ai (e.g. `5h = 30%`).
3. `budget = sum / (percent / 100)` → `3.6M / 0.30 = 12M`.
4. Set the env var (see below) to that value.

After calibrating, the widget tracks claude.ai closely.

## Configuration (environment variables)

- `CLAUDE_5H_BUDGET` — weighted-token budget for the 5-hour window
  (default `6000000`).
- `CLAUDE_WEEKLY_BUDGET` — weighted-token budget for the 7-day window
  (default `60000000`).
- `CLAUDE_W_INPUT` / `CLAUDE_W_OUTPUT` / `CLAUDE_W_CACHE_READ` /
  `CLAUDE_W_CACHE_WRITE` — per-token weights (defaults `1` / `5` / `0.1` /
  `1.25`).
- `CLAUDE_IDLE_MINUTES` — minutes without transcript writes before the label
  greys out (default `30`).

Set these in the genmon command line, e.g. edit the rc `Command=` to:

```
Command=env CLAUDE_5H_BUDGET=12000000 /path/to/claude-token-genmon.py
```

### Editing the rc safely (important)

A **running** xfce4-panel owns `~/.config/xfce4/panel/genmon-<id>.rc` and
rewrites it from its in-memory state whenever it restarts — so editing the file
under a live panel gets silently clobbered. To change `Command`, `Font`, etc.:

```sh
# write the rc FIRST, then hard-kill the panel so it can't save over your edit
pkill -9 -x xfce4-panel        # the session respawns it, reading your new rc
```

When driving this from a non-login shell, export the panel's session vars first
(`DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`) — read them from
`/proc/$(pgrep -x xfce4-panel)/environ`.

To remove the widget: right-click it → *Remove*.
