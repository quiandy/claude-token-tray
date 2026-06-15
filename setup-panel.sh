#!/usr/bin/env bash
# Add the Claude token widget to the xfce4 panel as a genmon plugin.
#
# Copyright (C) 2026 Andrea Chiarini
# SPDX-License-Identifier: LGPL-3.0-or-later
set -euo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/claude-token-genmon.py"
CHANNEL=xfce4-panel

if ! dpkg -s xfce4-genmon-plugin >/dev/null 2>&1; then
    echo "xfce4-genmon-plugin is not installed. Run:" >&2
    echo "  sudo apt install xfce4-genmon-plugin" >&2
    exit 1
fi

# Reuse an existing genmon instance pointing at our script, if any.
existing=$(xfconf-query -c $CHANNEL -p /plugins -lv 2>/dev/null \
    | awk '$2 == "genmon" {print $1}' | grep -oE '[0-9]+$' || true)
for id in $existing; do
    rc="$HOME/.config/xfce4/panel/genmon-$id.rc"
    if [ -f "$rc" ] && grep -q "$SCRIPT" "$rc"; then
        echo "Widget already configured as plugin-$id"
        # Newer genmon reads the command from xfconf; if a panel blanked it
        # (the "(genmon)" placeholder bug) point the user at the repair script.
        cur=$(xfconf-query -c $CHANNEL -p "/plugins/plugin-$id/command" 2>/dev/null || true)
        if [[ "$cur" != *claude-token-genmon.py* ]]; then
            echo "  note: its xfconf command is blank — run ./fix-tray.sh to restore it." >&2
        fi
        exit 0
    fi
done

# Next free plugin id.
max=$(xfconf-query -c $CHANNEL -p /plugins -l \
    | grep -oE '/plugins/plugin-[0-9]+$' | grep -oE '[0-9]+' | sort -n | tail -1)
id=$((max + 1))

mkdir -p "$HOME/.config/xfce4/panel"
cat > "$HOME/.config/xfce4/panel/genmon-$id.rc" <<EOF
Command=$SCRIPT
UpdatePeriod=5000
Text=
UseLabel=0
Font=Sans 11
EOF

xfconf-query -c $CHANNEL -p "/plugins/plugin-$id" -n -t string -s genmon

# Newer xfce4-genmon-plugin versions read their settings from xfconf rather than
# the rc file written above, so set them there too — the same command takes
# effect regardless of plugin version. (The rc stays as the source fix-tray.sh
# restores the command from if a panel ever blanks the xfconf copy.)
xfconf-query -c $CHANNEL -p "/plugins/plugin-$id/command"       -n -t string -s "$SCRIPT"
xfconf-query -c $CHANNEL -p "/plugins/plugin-$id/use-label"     -n -t bool   -s false
xfconf-query -c $CHANNEL -p "/plugins/plugin-$id/update-period" -n -t int    -s 5000
xfconf-query -c $CHANNEL -p "/plugins/plugin-$id/font"          -n -t string -s "Sans 11"

# Append the new id to the first panel's plugin list, before the last two
# items (typically pulseaudio/clock) so it lands near the status icons.
panel=$(xfconf-query -c $CHANNEL -p /panels | grep -oE '^[0-9]+' | head -1)
panel=${panel:-1}
mapfile -t ids < <(xfconf-query -c $CHANNEL -p "/panels/panel-$panel/plugin-ids" | grep -E '^[0-9]+$')
insert=$(( ${#ids[@]} - 2 )); [ $insert -lt 0 ] && insert=${#ids[@]}
new_ids=("${ids[@]:0:insert}" "$id" "${ids[@]:insert}")

args=()
for i in "${new_ids[@]}"; do args+=(-t int -s "$i"); done
xfconf-query -c $CHANNEL -p "/panels/panel-$panel/plugin-ids" --force-array "${args[@]}"

# Restart the panel; if it doesn't survive (e.g. when run from a non-session
# shell), relaunch it detached so it isn't tied to this script's lifetime.
xfce4-panel -r || true
sleep 3
if ! pgrep -x xfce4-panel >/dev/null; then
    setsid -f xfce4-panel >/dev/null 2>&1
fi
echo "Added genmon plugin-$id to panel-$panel"
