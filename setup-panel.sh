#!/usr/bin/env bash
# Add the Claude token widget to the xfce4 panel as a genmon plugin.
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
Font=(none)
EOF

xfconf-query -c $CHANNEL -p "/plugins/plugin-$id" -n -t string -s genmon

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
