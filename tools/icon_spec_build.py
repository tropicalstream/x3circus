#!/usr/bin/env python3
"""
Emit tools/icon_spec.json: BOTH CLOWNS ON THE SEESAW.

The clown here is a direct transcription of Game.kt drawClown - every feature is
the same multiple of r that the game uses, so the launcher mark is genuinely the
same character the player sees and not a lookalike redrawn by eye.

ONE COORDINATE FLIP TO WATCH: the game's y axis points UP, an icon viewport's
points DOWN, so every y offset is negated on the way in.
"""
import json
import math
import sys

# Palette, converted from the game's float rgb.
BOOT   = "#FFD940"   # 1.00, 0.85, 0.25
LEG    = "#80FFE6"   # 0.50, 1.00, 0.90
# Limbs get their own hue in the icon. The game's cyan limbs are fine against a
# black playfield, but here they sat one step away from the plank's #66E6FF and
# the two kept merging into a single shape.
ARM    = "#9CFFC4"
COLLAR = "#FF59A6"   # 1.00, 0.35, 0.65
SKIN   = "#FFBF8C"   # 1.00, 0.75, 0.55
HEAD   = "#FFD999"   # 1.00, 0.85, 0.60
HAIR   = "#FF593F"   # 1.00, 0.35, 0.25
HAT    = "#59D9FF"   # 0.35, 0.85, 1.00
POM    = "#FFE659"   # 1.00, 0.90, 0.35
NOSE   = "#FF3333"   # 1.00, 0.20, 0.20
GRIN   = "#FF4D4D"   # 1.00, 0.30, 0.30
PLANK  = "#66E6FF"
PIVOT  = "#FF8A3D"
GROUND = "#FF8A3D"


def clown(cx, cy, r, arms, sw, detail=True, hair=2, headfill=True, grin=True):
    """cx,cy is the HEAD centre. arms: 'up' or an angle in radians."""
    p = []
    L = lambda x1, y1, x2, y2, c, w: p.append(
        {"t": "line", "x1": round(x1, 2), "y1": round(y1, 2),
         "x2": round(x2, 2), "y2": round(y2, 2), "w": round(w, 2), "c": c, "a": 1.0})
    C = lambda x, y, rr, c, w, a=1.0: p.append(
        {"t": "circle", "cx": round(x, 2), "cy": round(y, 2), "r": round(rr, 2),
         "w": round(w, 2), "c": c, "a": a})

    booty = cy + 1.47 * r
    # Boots - comically wide, and the first thing you notice.
    L(cx - 1.46 * r, booty, cx - 0.42 * r, booty, BOOT, sw * 1.30)
    L(cx + 0.42 * r, booty, cx + 1.46 * r, booty, BOOT, sw * 1.30)
    # Legs.
    L(cx - 0.55 * r, cy + r, cx - 1.04 * r, booty, LEG, sw)
    L(cx + 0.55 * r, cy + r, cx + 1.04 * r, booty, LEG, sw)
    # Ruffle collar: three scallops is all it takes to read as one.
    # Pushed down and spread wider than the game's, so it reads as a collar
    # UNDER the head rather than a second ring around it.
    for k in (-1, 0, 1):
        C(cx + k * 0.66 * r, cy + 0.92 * r, 0.34 * r, COLLAR, sw * 0.85)
    # Head.
    if headfill:
        p.append({"t": "disc", "cx": round(cx, 2), "cy": round(cy, 2),
                  "rx": round(0.82 * r, 2), "ry": round(0.86 * r, 2),
                  "c": SKIN, "a": 0.50})
    C(cx, cy, r, HEAD, sw)
    # Hair: TWO tufts a side here, not the game's three. At icon scale three
    # tufts plus the collar merge into one pink halo and the clown loses his
    # head outline entirely; dropping the middle one keeps the spikes readable.
    for s in (-1, 1):
        hx = cx + s * 0.95 * r
        if hair >= 1:
            L(hx, cy + 0.30 * r, hx + s * 0.62 * r, cy + 0.56 * r, HAIR, sw)
        if hair >= 2:
            L(hx, cy - 0.17 * r, hx + s * 0.62 * r, cy - 0.52 * r, HAIR, sw)
    # Cone hat with a pompom.
    L(cx - 0.80 * r, cy - 0.80 * r, cx + 0.80 * r, cy - 0.80 * r, HAT, sw)
    L(cx - 0.61 * r, cy - 0.80 * r, cx, cy - 1.94 * r, HAT, sw)
    L(cx + 0.61 * r, cy - 0.80 * r, cx, cy - 1.94 * r, HAT, sw)
    C(cx, cy - 2.08 * r, 0.25 * r, POM, sw * 0.85)
    # Face. The nose and the grin carry it; the eyes are the first thing to go
    # when the icon is small, because at 48px they are sub-pixel anyway.
    # The eyes are sub-pixel below ~150px and only ever muddied the face, so
    # they are drawn as bright dots rather than the game's dark ones - on an
    # additive display a dark dot on a dim head is simply not there.
    if detail:
        for s in (-1, 1):
            C(cx + s * 0.38 * r, cy - 0.26 * r, 0.10 * r, "#FFFFFF", sw * 0.6)
    C(cx, cy + 0.06 * r, 0.30 * r, NOSE, sw * 0.9)
    if grin:
        L(cx - 0.58 * r, cy + 0.36 * r, cx - 0.25 * r, cy + 0.64 * r, GRIN, sw * 0.9)
        L(cx - 0.25 * r, cy + 0.64 * r, cx + 0.25 * r, cy + 0.64 * r, GRIN, sw * 0.9)
        L(cx + 0.25 * r, cy + 0.64 * r, cx + 0.58 * r, cy + 0.36 * r, GRIN, sw * 0.9)
    # Arms. THEY HANG OFF THE COLLAR, NOT THE HEAD. The game draws a whole body
    # under the head; the icon does not, so arms radiating from the head centre
    # crossed the face and combined with the hair into a starburst that read as
    # a spiky ball rather than a clown.
    # SHORT AND STEEP. Long shallow arms in the same cyan as the plank read as
    # the clown holding a pole, and the left one's arm ran straight into the
    # plank end. Up-and-out at ~50 degrees separates them from every other line
    # in the composition.
    sx, sy = 0.60 * r, 0.86 * r
    if arms == "up":
        L(cx - sx, cy + sy, cx - 1.34 * r, cy - 0.22 * r, ARM, sw)
        L(cx + sx, cy + sy, cx + 1.34 * r, cy - 0.22 * r, ARM, sw)
    else:
        L(cx - sx, cy + sy, cx - 1.30 * r, cy - 0.34 * r, ARM, sw)
        L(cx + sx, cy + sy, cx + 1.24 * r, cy + 0.74 * r, ARM, sw)
    return p


def bbox(prims):
    xs, ys = [], []
    for p in prims:
        t = p["t"]
        if t == "line":
            xs += [p["x1"], p["x2"]]; ys += [p["y1"], p["y2"]]
        elif t == "circle":
            xs += [p["cx"] - p["r"], p["cx"] + p["r"]]
            ys += [p["cy"] - p["r"], p["cy"] + p["r"]]
        elif t == "disc":
            xs += [p["cx"] - p["rx"], p["cx"] + p["rx"]]
            ys += [p["cy"] - p["ry"], p["cy"] + p["ry"]]
        elif t == "poly":
            xs += [q[0] for q in p["pts"]]; ys += [q[1] for q in p["pts"]]
    return min(xs), max(xs), min(ys), max(ys)


def fit(prims, lo=22.0, hi=86.0):
    """Scale and centre the whole composition to fill the adaptive-icon safe
    zone. Designing at a comfortable scale and fitting afterwards beats hand-
    tuning coordinates, and it guarantees the art is as large as the mask allows
    instead of floating in dead space."""
    x0, x1, y0, y1 = bbox(prims)
    span = max(x1 - x0, y1 - y0)
    k = (hi - lo) / span
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    mid = (lo + hi) / 2
    T = lambda x, y: (round(mid + (x - cx) * k, 2), round(mid + (y - cy) * k, 2))
    for p in prims:
        t = p["t"]
        if t == "line":
            p["x1"], p["y1"] = T(p["x1"], p["y1"])
            p["x2"], p["y2"] = T(p["x2"], p["y2"])
        elif t == "circle":
            p["cx"], p["cy"] = T(p["cx"], p["cy"]); p["r"] = round(p["r"] * k, 2)
        elif t == "disc":
            p["cx"], p["cy"] = T(p["cx"], p["cy"])
            p["rx"] = round(p["rx"] * k, 2); p["ry"] = round(p["ry"] * k, 2)
        elif t == "poly":
            p["pts"] = [list(T(q[0], q[1])) for q in p["pts"]]
        if "w" in p:
            p["w"] = round(max(p["w"] * k, 1.6), 2)
    return prims


def build(r=9.0, sw=2.2, detail=True, ground=True, hair=1, headfill=False, grin=True):
    """Defaults are what survived looking at the thing at 48, 96 and 432 px.

    r=9 rather than the 6 the composition started at: below about r=8 the clowns
    collapse into blobs at 48 px and only the hats stay readable. headfill off
    and one hair tuft a side rather than the game's three, because at icon scale
    the head outline, the head fill, the hair and the collar all sit within 2r of
    each other and merge into one pink halo."""
    prims = []
    # The plank. Low end left, raised end right - the same asymmetry the game
    # draws, which is what makes it read as a seesaw and not a plus sign.
    lx, ly = 28.0, 80.0
    rx, ry = 80.0, 58.0
    mx, my = (lx + rx) / 2, (ly + ry) / 2

    if ground:
        prims.append({"t": "line", "x1": 20, "y1": 86, "x2": 88, "y2": 86,
                      "w": 2.0, "c": GROUND, "a": 0.85})
    # Fulcrum.
    prims.append({"t": "poly", "pts": [[mx - 6, 86], [mx + 6, 86], [mx, my + 1]],
                  "w": 2.2, "c": PIVOT, "a": 1.0, "close": True,
                  "fill": PIVOT, "fa": 0.22})
    # Plank.
    prims.append({"t": "line", "x1": lx, "y1": ly, "x2": rx, "y2": ry,
                  "w": 3.0, "c": PLANK, "a": 1.0})

    # A clown at each end, standing ON the plank: head centre is one boot-height
    # above the plank surface.
    lift = 1.47 * r + 1.5
    slope = (ry - ly) / (rx - lx)
    for ex, arms in ((lx + 5, "up"), (rx - 5, -0.9)):
        ey = ly + (ex - lx) * slope
        prims += clown(ex, ey - lift, r, arms, sw, detail, hair, headfill, grin)
    return fit(prims)


if __name__ == "__main__":
    kw = {}
    for a in sys.argv[1:]:
        k, _, v = a.partition("=")
        kw[k.lstrip("-")] = float(v) if v.replace(".", "").isdigit() else (v != "0")
    prims = build(**kw)
    out = {"name": "two clowns on the seesaw", "prims": prims}
    import os
    dest = os.environ.get("ICON_SPEC_OUT",
                          "/Users/me/Projects/x3circus/tools/icon_spec.json")
    json.dump(out, open(dest, "w"), indent=1)
    xs, ys = [], []
    for p in prims:
        if p["t"] == "line":
            xs += [p["x1"], p["x2"]]; ys += [p["y1"], p["y2"]]
        elif p["t"] == "circle":
            xs += [p["cx"] - p["r"], p["cx"] + p["r"]]; ys += [p["cy"] - p["r"], p["cy"] + p["r"]]
        elif p["t"] == "disc":
            xs += [p["cx"] - p["rx"], p["cx"] + p["rx"]]; ys += [p["cy"] - p["ry"], p["cy"] + p["ry"]]
        elif p["t"] == "poly":
            xs += [q[0] for q in p["pts"]]; ys += [q[1] for q in p["pts"]]
    print("%d primitives, bbox x %.1f..%.1f  y %.1f..%.1f  (safe zone 21..87)"
          % (len(prims), min(xs), max(xs), min(ys), max(ys)))
