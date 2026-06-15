# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Idle detection is now based on whether a Claude Code session (`claude`
  process) is actually running, checked on every ~5 s panel tick, rather than on
  transcript write times. With no session running the widget **suspends polling
  entirely** and dims the whole label to a darker grey, resuming on the next
  tick once a session reappears. While a session is running it polls on the
  usual `CLAUDE_LIVE_MIN_POLL` cadence.
- Cached/back-off data is now labelled honestly as cached (and greyed once
  stale) instead of being shown as `live`.

### Added
- `CLAUDE_LIVE_BACKOFF_SECONDS` (default 300): caps how long a 429 `Retry-After`
  may suppress polling, so an unusually long value can no longer freeze the
  panel on a stale snapshot for hours.
- `CLAUDE_IDLE_COLOUR` (default `#666666`): the colour the label dims to when
  idle.

### Removed
- `CLAUDE_IDLE_MINUTES` — superseded by the session-presence check.

### Fixed
- A long 429 `Retry-After` from `/api/oauth/usage` could freeze the panel on a
  hours-old snapshot while still labelling it `live`.

## [1.0.0] - 2026-06-14

First public release.

### Added
- Live, exact usage percentages read from `GET /api/oauth/usage` (the same
  source as Claude Code's `/usage`), matching claude.ai with no calibration.
- 5-hour and 7-day windows with reset times, colour thresholds (amber ≥70%,
  red ≥90%), and an idle-grey state.
- Small Anthropic-style logo shown before the text (`assets/anthropic.png`,
  overridable via `CLAUDE_TRAY_ICON`).
- Rate-limit handling: minimum poll interval plus `Retry-After`-aware backoff,
  so the 5-second panel refresh never hammers the endpoint.
- Offline fallback: transcript-based weighted-token estimate, labelled `(est)`.
- `setup-panel.sh` installer for Xfce GenMon.
- Comprehensive `unittest` suite and GitHub Actions CI.

[Unreleased]: https://github.com/quiandy/claude-token-tray/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/quiandy/claude-token-tray/releases/tag/v1.0.0
