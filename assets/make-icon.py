#!/usr/bin/env python3
#
# Copyright (C) 2026 Andrea Chiarini
# SPDX-License-Identifier: LGPL-3.0-or-later
#
# Regenerate assets/anthropic.png -- a small Anthropic-style "burst" mark drawn
# in the brand clay/coral colour, on a transparent background, sized for an Xfce
# panel. This is a build-time helper and needs Pillow (`pip install pillow`); the
# widget itself has no third-party dependencies.
#
#   python3 assets/make-icon.py
#
# NOTE: "Anthropic" and the Anthropic logo are trademarks of Anthropic. The icon
# produced here is a simple stylised burst, not the official logo asset; swap in
# your own image (or set CLAUDE_TRAY_ICON) if you prefer.
import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 22          # final panel size in px
SS = 8             # supersampling factor for smooth edges
CLAY = (217, 119, 87, 255)   # Anthropic clay / coral (#D97757)
SPOKES = 8

px = SIZE * SS
img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

c = px / 2
tip_r = px * 0.47          # spoke length from centre
base_w = px * 0.115        # half-width of each spoke at its mid-point

for i in range(SPOKES):
    a = math.pi * 2 * i / SPOKES
    ca, sa = math.cos(a), math.sin(a)
    # perpendicular direction for the spoke's width
    pa, ps = math.cos(a + math.pi / 2), math.sin(a + math.pi / 2)
    tip = (c + ca * tip_r, c + sa * tip_r)
    mid = (c + ca * tip_r * 0.42, c + sa * tip_r * 0.42)
    left = (mid[0] + pa * base_w, mid[1] + ps * base_w)
    right = (mid[0] - pa * base_w, mid[1] - ps * base_w)
    draw.polygon([tip, left, (c, c), right], fill=CLAY)

# soft round centre so the spokes meet cleanly
draw.ellipse([c - base_w, c - base_w, c + base_w, c + base_w], fill=CLAY)

img = img.resize((SIZE, SIZE), Image.LANCZOS)
out = Path(__file__).resolve().parent / "anthropic.png"
img.save(out)
print(f"wrote {out} ({SIZE}x{SIZE})")
