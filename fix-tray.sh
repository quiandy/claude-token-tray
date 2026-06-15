#!/usr/bin/env bash
# Repair the Claude token GenMon widget when the Xfce panel forgets its command.
#
# Newer xfce4-genmon-plugin versions keep their configuration in xfconf rather
# than the genmon-<id>.rc file. After an unclean shutdown or reboot the panel
# can flush an empty in-memory state back to xfconf, blanking the plugin's
# command -- so the widget shows only the "(genmon)" placeholder. A plain
# `xfce4-panel -r` does not help: the restarting panel re-saves that empty
# state over any value you write. The command must be restored while the panel
# is stopped, then read back in by a fresh panel. This script does exactly that.
#
# Copyright (C) 2026 Andrea Chiarini
# SPDX-License-Identifier: LGPL-3.0-or-later
set -euo pipefail

CHANNEL=xfce4-panel
SCRIPT="$(cd "$(dirname "$0")" && pwd)/claude-token-genmon.py"

command -v xfconf-query >/dev/null 2>&1 || {
    echo "xfconf-query not found (is this an Xfce session?)" >&2; exit 1
}

# When run from a non-login shell, borrow the session vars from a running panel
# so xfconf-query and the restart can reach the right display/bus.
if [ -z "${DISPLAY:-}" ] || [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    panel_pid=$(pgrep -x xfce4-panel | head -1 || true)
    if [ -n "$panel_pid" ] && [ -r "/proc/$panel_pid/environ" ]; then
        while IFS= read -r -d '' kv; do
            case "$kv" in
                DISPLAY=*|DBUS_SESSION_BUS_ADDRESS=*|XAUTHORITY=*) export "$kv" ;;
            esac
        done < "/proc/$panel_pid/environ"
    fi
fi

# Find our GenMon plugin id. Prefer a live xfconf command that already points at
# our script; otherwise -- the blanked case -- match the genmon-<id>.rc that
# references it. The .rc survives the blanking and also preserves any
# CLAUDE_*_BUDGET env the command line carried.
find_plugin_id() {
    local p id cmd rc
    for p in $(xfconf-query -c "$CHANNEL" -p /plugins -lv 2>/dev/null \
            | awk '$2 == "genmon" {print $1}'); do
        id=$(grep -oE '[0-9]+$' <<<"$p")
        cmd=$(xfconf-query -c "$CHANNEL" -p "/plugins/plugin-$id/command" 2>/dev/null || true)
        if [[ "$cmd" == *claude-token-genmon.py* ]]; then echo "$id"; return; fi
    done
    for rc in "$HOME"/.config/xfce4/panel/genmon-*.rc; do
        [ -f "$rc" ] || continue
        if grep -q claude-token-genmon.py "$rc"; then
            grep -oE 'genmon-[0-9]+' <<<"$rc" | grep -oE '[0-9]+'; return
        fi
    done
}

id=$(find_plugin_id || true)
if [ -z "${id:-}" ]; then
    echo "No GenMon plugin for claude-token-genmon.py found." >&2
    echo "Run ./setup-panel.sh first to create the widget." >&2
    exit 1
fi

# Restore the exact command from the rc Command= line if present (keeps env
# vars); otherwise just the script path.
rc="$HOME/.config/xfce4/panel/genmon-$id.rc"
if [ -f "$rc" ] && grep -q '^Command=' "$rc"; then
    CMD=$(sed -n 's/^Command=//p' "$rc" | head -1)
else
    CMD="$SCRIPT"
fi

echo "Repairing GenMon plugin-$id"
echo "  command: $CMD"

# Stop the panel so it cannot overwrite what we write next.
xfce4-panel -q >/dev/null 2>&1 || true
sleep 2

set_prop() {  # property type value
    xfconf-query -c "$CHANNEL" -p "/plugins/plugin-$id/$1" -s "$3" 2>/dev/null \
        || xfconf-query -c "$CHANNEL" -p "/plugins/plugin-$id/$1" -n -t "$2" -s "$3"
}
set_prop command string "$CMD"
set_prop use-label bool false       # we draw our own label via <txt>
set_prop update-period int 5000

# Start the panel fresh so it reads the restored command into memory.
setsid -f xfce4-panel >/dev/null 2>&1 || setsid xfce4-panel >/dev/null 2>&1 &
sleep 3

if [ "$(xfconf-query -c "$CHANNEL" -p "/plugins/plugin-$id/command" 2>/dev/null)" = "$CMD" ] \
        && pgrep -x xfce4-panel >/dev/null; then
    echo "Done. plugin-$id restored and panel restarted."
else
    echo "Restarted, but the command did not stick -- check the panel." >&2
    exit 1
fi
