# claude-token-tray

[![CI](https://github.com/quiandy/claude-token-tray/actions/workflows/ci.yml/badge.svg)](https://github.com/quiandy/claude-token-tray/actions/workflows/ci.yml)
[![License: LGPL v3](https://img.shields.io/badge/License-LGPL_v3-blue.svg)](COPYING.LESSER)

An Xfce panel ([GenMon](https://docs.xfce.org/panel-plugins/xfce4-genmon-plugin/start))
widget that shows your **Claude Code** subscription usage across the **5-hour**
and **weekly** windows, matching what `claude /usage` and claude.ai report.

```
✳ 5h 14% · 7d 6% · ↻02:40
```

- the leading mark is a small Anthropic-style logo (`assets/anthropic.png`); the
  `✳` above is the text fallback shown when no icon image is available
- `5h 14%` — usage of the current 5-hour window
- `7d 6%` — usage of the rolling 7-day window (turns amber ≥70%, red ≥90%)
- `↻02:40` — when the current 5-hour window resets

The label greys out when no Claude Code session has written for a while. Hover
the widget for both percentages, reset times, and any extra-usage (overage)
status.

## Requirements

This is a single Python script plus an installer; there are **no third-party
Python packages to install** (standard library only).

| Requirement | Notes |
|---|---|
| Linux + **Xfce** desktop | Uses the Xfce panel and `xfconf`. |
| **`xfce4-genmon-plugin`** | The GenMon panel plugin. `sudo apt install xfce4-genmon-plugin` (or your distro's equivalent). |
| **Python ≥ 3.8** | Standard library only — no `pip install` needed. |
| **Claude Code**, signed in | Provides the OAuth token at `~/.claude/.credentials.json` and the transcripts under `~/.claude/projects/`. |
| A Claude **subscription** (Pro/Max) | The usage windows are a subscription feature. |
| Network access to `api.anthropic.com` | For the live percentages. Without it the widget falls back to an offline estimate. |

## Quick start

```sh
sudo apt install xfce4-genmon-plugin     # Debian/Ubuntu — see below for others
git clone https://github.com/quiandy/claude-token-tray.git
cd claude-token-tray
./setup-panel.sh
```

Installing the GenMon plugin on other distros:

| Distro | Command |
|---|---|
| Debian / Ubuntu | `sudo apt install xfce4-genmon-plugin` |
| Fedora | `sudo dnf install xfce4-genmon-plugin` |
| Arch | `sudo pacman -S xfce4-genmon-plugin` |
| openSUSE | `sudo zypper install xfce4-genmon-plugin` |

`setup-panel.sh` registers a new GenMon instance on the first panel (next to the
status icons) refreshing every 5 seconds. To check the script alone without the
panel, just run it:

```sh
./claude-token-genmon.py
```

It prints the GenMon XML (`<txt>…</txt><tool>…</tool>`) to stdout.

> **Font note:** the GenMon font must be a real font (the installer sets
> `Sans 11`). A `Font=(none)` value renders the label invisibly while still
> drawing the widget.

To remove the widget later: right-click it → *Remove*.

## How it works

Anthropic meters subscription usage as a server-side **utilization percentage**
over a 5-hour window (anchored to your first message) and a 7-day window. There
is no fixed local "token budget" for a plan — the effective allowance is dynamic
(it varies with model, caching, and demand), so only the percentage is
meaningful, and that percentage *is* retrievable.

`claude-token-genmon.py` reads the real numbers directly from the same source
Claude Code's own `/usage` command uses:

```
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <token from ~/.claude/.credentials.json>
anthropic-beta: oauth-2025-04-20
```

which returns, e.g.:

```json
{"five_hour": {"utilization": 14.0, "resets_at": "...Z"},
 "seven_day": {"utilization": 6.0, "resets_at": "...Z"},
 "extra_usage": {"is_enabled": false, ...}}
```

So the panel matches claude.ai exactly — no token-summing, no budgets, no
calibration. (The same `utilization`/`reset` values are also broadcast on every
API response as `anthropic-ratelimit-unified-{five_hour,seven_day}-*` headers;
the endpoint is just easier to poll.) The last good response is cached in
`~/.cache/claude-token-tray/usage.json`.

### Polling and rate limits

The panel refreshes every ~5 seconds, but `/api/oauth/usage` is **itself
rate-limited** (HTTP 429 with a `Retry-After` of a few minutes), and utilization
moves slowly. So the widget polls at most once per `CLAUDE_LIVE_MIN_POLL`
seconds (default 180) and serves the cache in between. If it does get a 429, it
honours `Retry-After` and keeps showing the last good numbers until the window
clears.

### Fallback estimate

If the API is unreachable (offline, or an expired OAuth token it can't refresh),
the widget falls back to a **legacy estimate**: it sums per-message `usage` from
`~/.claude/projects/*/*.jsonl` over each window, weights the tokens
(output/cache-write up, cache-read down), and divides by a configurable budget.
This path is approximate — it is labelled `(est)` in the panel — and exists only
so the widget shows *something* offline. A cached live result younger than
`CLAUDE_LIVE_STALE_SECONDS` (default 15 min) is preferred over the estimate.

## Configuration (environment variables)

The live path needs no configuration. These tune behaviour and the offline
fallback:

| Variable | Default | Purpose |
|---|---|---|
| `CLAUDE_TRAY_ICON` | `assets/anthropic.png` | Image shown before the text. Set to a different path to use your own, or to empty to fall back to the `✳` glyph. |
| `CLAUDE_IDLE_MINUTES` | `30` | Minutes without transcript writes before the label greys out. |
| `CLAUDE_HTTP_TIMEOUT` | `4` | Seconds to wait on the usage API. |
| `CLAUDE_LIVE_MIN_POLL` | `180` | Minimum seconds between API polls; the cache is reused in between. |
| `CLAUDE_LIVE_STALE_SECONDS` | `900` | How long a cached live result is shown when the API is unreachable before falling back to the estimate. |
| `CLAUDE_5H_BUDGET` / `CLAUDE_WEEKLY_BUDGET` | `6000000` / `60000000` | *Estimate only:* weighted-token budgets. |
| `CLAUDE_W_INPUT` / `CLAUDE_W_OUTPUT` / `CLAUDE_W_CACHE_READ` / `CLAUDE_W_CACHE_WRITE` | `1` / `5` / `0.1` / `1.25` | *Estimate only:* per-token weights. |

Set these in the GenMon command line, e.g. edit the rc `Command=` to:

```
Command=env CLAUDE_HTTP_TIMEOUT=6 /path/to/claude-token-genmon.py
```

> The estimate's budgets are crude guesses, only used offline. If you want the
> fallback to be less wrong, calibrate once:
> `budget = weighted_sum / (claude.ai_percent / 100)`.

## Security & privacy

- The widget reads your Claude OAuth token from `~/.claude/.credentials.json`
  and sends it **only** to `https://api.anthropic.com` — the same endpoint
  Claude Code itself calls. Nothing is sent to any third party.
- The token never leaves your machine except in that request, and is not logged
  or written anywhere by this tool. The only thing cached on disk is the usage
  response (percentages and reset times) in `~/.cache/claude-token-tray/`.
- It runs entirely as your user; no elevated privileges (the one `sudo` is just
  to install the GenMon package).

## Troubleshooting

**The label is invisible / blank.** The GenMon font is unset. Set it to a real
font (see the font note above).

**Shows `(est)` instead of live numbers.** The API call isn't succeeding —
you're offline, the OAuth token expired (re-run Claude Code to refresh it), or
you've been rate-limited (it recovers automatically within a few minutes).

**My panel edits keep getting reverted.** A *running* xfce4-panel owns
`~/.config/xfce4/panel/genmon-<id>.rc` and rewrites it from memory on restart,
so editing under a live panel gets clobbered. Write the rc first, then hard-kill
the panel so the session respawns it from your file:

```sh
pkill -9 -x xfce4-panel        # the session respawns it, reading your new rc
```

When driving this from a non-login shell, export the panel's session vars first
(`DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`) — read them from
`/proc/$(pgrep -x xfce4-panel)/environ`.

## Development

Tests are pure standard-library `unittest` (no dependencies). They sandbox all
filesystem state into a temp dir and stub the network, so they never touch your
real `~/.claude` or contact the API:

```sh
python3 -m unittest -v        # or: pytest -v
```

CI runs the suite on every push and pull request (see
`.github/workflows/ci.yml`).

## Contributing

Contributions are welcome — please **open a pull request**:

1. Fork the repo and create a branch.
2. Make your change. Keep it dependency-free (standard library only) and match
   the existing style.
3. Add or update tests, and make sure `python3 -m unittest` passes.
4. Open a PR describing the change. For larger changes, opening an issue first
   to discuss is appreciated.

Bug reports and feature ideas are also welcome via GitHub issues.

## Trademarks

"Anthropic" and "Claude" are trademarks of Anthropic. This is an unofficial,
community project and is not affiliated with or endorsed by Anthropic. The
bundled `assets/anthropic.png` is a simple stylised mark (regenerate it with
`assets/make-icon.py`), not the official logo asset — set `CLAUDE_TRAY_ICON` to
swap it for your own.

## License

[GNU Lesser General Public License v3.0 or later](COPYING.LESSER) (LGPL-3.0-or-later).
See [`COPYING.LESSER`](COPYING.LESSER) and [`COPYING`](COPYING) for the full
text.
