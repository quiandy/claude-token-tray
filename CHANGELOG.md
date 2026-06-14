# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/quiandy/claude-token-tray/releases/tag/v1.0.0
