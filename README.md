# claude-token-tray

Xfce panel (genmon) widget showing token usage of the most recent Claude Code
session.

The panel shows `✳ 18.9k` — the current context-window size of the latest
active session — with a hover tooltip giving the model, input/cache breakdown,
last reply size and timestamp. The label turns grey when the session has been
idle for 30 minutes.

## How it works

`claude-token-genmon.py` picks the most recently modified transcript under
`~/.claude/projects/*/*.jsonl`, reads the last assistant message's `usage`
block, and prints xfce4-genmon-plugin XML. Context usage is
`input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.

## Install

```sh
sudo apt install xfce4-genmon-plugin
./setup-panel.sh
```

`setup-panel.sh` registers a new genmon instance on the first panel (next to
the status icons) refreshing every 5 seconds.

## Configuration (environment variables)

- `CLAUDE_CONTEXT_LIMIT` — context window size used for the percentage
  (default `200000`; set `1000000` for 1M-context models).
- `CLAUDE_IDLE_MINUTES` — minutes without transcript writes before the label
  greys out (default `30`).

To remove the widget: right-click it → *Remove*.
