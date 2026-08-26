#!/usr/bin/env python3
"""
Build the x3circus launcher icon from a list of drawing primitives.

WHY THIS EXISTS AND WHY IT HAS NO DEPENDENCIES: this machine has no PIL, no
cairo and no SVG rasteriser, and the icon has to be regenerated whenever the
in-game art changes. So this is a small supersampled scanline rasteriser plus a
zlib PNG writer, which is all the job actually needs.

It emits BOTH halves of an Android icon from one source of truth:
  - res/drawable/ic_circus_foreground.xml   adaptive-icon foreground (vector)
  - res/mipmap-*/ic_launcher_fg.png         adaptive foreground raster
  - res/mipmap-*/ic_launcher.png            legacy square icon, over the purple

The art is drawn ADDITIVELY over black, because that is how the game itself
renders: the X3's waveguide is additive, so a "glow" is just the same stroke
laid down several times, wide and faint underneath, narrow and bright on top.

Coordinates are image coordinates in a 108x108 viewport: x right, y DOWN.

Usage:  make_icon.py spec.json [--out <res dir>] [--preview <dir>]
"""

import json
import math
import os
import struct
import sys
import zlib
from array import array

VIEW = 108.0
BG = (0x1A, 0x0B, 0x2E)          # ic_launcher_background
SS = 3                            # supersampling factor per axis

# Legacy square icons, and adaptive foregrounds (108dp at each density).
LEGACY = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
FOREGR = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}

# Glow stack: (width multiplier, alpha multiplier). Wide+faint first, so the
# bright core lands on top. Three passes is enough; more just costs time.
# Measured, not guessed: the wide 3.2x/0.10 pass piled up over every overlapping
# stroke and turned each clown into a white blob. Two passes at 2.2x keep a halo
# without eating the faces.
GLOW = ((2.2, 0.07), (1.0, 1.0))

# Overridable for tuning sweeps: ICON_GLOW="2.2:0.07,1.0:1.0" ICON_BLEND=screen
if os.environ.get("ICON_GLOW"):
    GLOW = tuple(tuple(float(x) for x in part.split(":"))
                 for part in os.environ["ICON_GLOW"].split(","))
# ADDITIVE SUMS PAST WHITE. The game gets away with it because its strokes are
# far apart; here a clown's features are 1-4 units apart with a 7-unit glow, so
# every overlap piles up and the whole figure saturates to a white blob. SCREEN
# blending rolls off instead of clipping, which keeps the hues.
BLEND = os.environ.get("ICON_BLEND", "screen")


def hex2rgb(s):
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class Canvas:
    """Additive float canvas. rgb accumulates light; cov tracks max coverage."""

    def __init__(self, n):
        self.n = n
        self.r = array("f", [0.0]) * (n * n)
        self.g = array("f", [0.0]) * (n * n)
        self.b = array("f", [0.0]) * (n * n)
        self.a = array("f", [0.0]) * (n * n)

    def add(self, x, y, col, w):
        if w <= 0.0:
            return
        i = y * self.n + x
        if BLEND == "add":
            self.r[i] += col[0] * w
            self.g[i] += col[1] * w
            self.b[i] += col[2] * w
        else:
            sr, sg, sb = col[0] * w, col[1] * w, col[2] * w
            self.r[i] = self.r[i] + sr * (1.0 - self.r[i])
            self.g[i] = self.g[i] + sg * (1.0 - self.g[i])
            self.b[i] = self.b[i] + sb * (1.0 - self.b[i])
        if w > self.a[i]:
            self.a[i] = w


def _seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    if L <= 1e-12:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / L
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _bbox(cv, xs, ys, pad):
    x0 = max(0, int(math.floor(min(xs) - pad)))
    x1 = min(cv.n - 1, int(math.ceil(max(xs) + pad)))
    y0 = max(0, int(math.floor(min(ys) - pad)))
    y1 = min(cv.n - 1, int(math.ceil(max(ys) + pad)))
    return x0, x1, y0, y1


def draw_line(cv, s, x1, y1, x2, y2, w, col, a):
    x1, y1, x2, y2, hw = x1 * s, y1 * s, x2 * s, y2 * s, (w * s) / 2.0
    x0b, x1b, y0b, y1b = _bbox(cv, (x1, x2), (y1, y2), hw + 1.5)
    for py in range(y0b, y1b + 1):
        fy = py + 0.5
        for px in range(x0b, x1b + 1):
            d = _seg_dist(px + 0.5, fy, x1, y1, x2, y2)
            c = hw + 0.5 - d
            if c > 0.0:
                cv.add(px, py, col, a * (1.0 if c >= 1.0 else c))


def draw_ring(cv, s, cx, cy, r, w, col, a):
    cx, cy, r, hw = cx * s, cy * s, r * s, (w * s) / 2.0
    x0b, x1b, y0b, y1b = _bbox(cv, (cx - r, cx + r), (cy - r, cy + r), hw + 1.5)
    for py in range(y0b, y1b + 1):
        dy = py + 0.5 - cy
        for px in range(x0b, x1b + 1):
            dx = px + 0.5 - cx
            c = hw + 0.5 - abs(math.hypot(dx, dy) - r)
            if c > 0.0:
                cv.add(px, py, col, a * (1.0 if c >= 1.0 else c))


def draw_disc(cv, s, cx, cy, rx, ry, col, a):
    cx, cy, rx, ry = cx * s, cy * s, max(rx * s, 1e-6), max(ry * s, 1e-6)
    x0b, x1b, y0b, y1b = _bbox(cv, (cx - rx, cx + rx), (cy - ry, cy + ry), 1.5)
    for py in range(y0b, y1b + 1):
        dy = (py + 0.5 - cy) / ry
        for px in range(x0b, x1b + 1):
            dx = (px + 0.5 - cx) / rx
            d = math.hypot(dx, dy)
            c = (1.0 - d) * min(rx, ry) + 0.5
            if c > 0.0:
                cv.add(px, py, col, a * (1.0 if c >= 1.0 else c))


def draw_fill(cv, s, pts, col, a):
    """Even-odd scanline fill, sampled at the supersampled grid."""
    P = [(x * s, y * s) for x, y in pts]
    xs = [p[0] for p in P]
    ys = [p[1] for p in P]
    x0b, x1b, y0b, y1b = _bbox(cv, xs, ys, 1.0)
    n = len(P)
    for py in range(y0b, y1b + 1):
        fy = py + 0.5
        xin = []
        for i in range(n):
            ax, ay = P[i]
            bx, by = P[(i + 1) % n]
            if (ay <= fy < by) or (by <= fy < ay):
                xin.append(ax + (fy - ay) * (bx - ax) / (by - ay))
        xin.sort()
        for k in range(0, len(xin) - 1, 2):
            for px in range(max(x0b, int(xin[k])), min(x1b, int(xin[k + 1])) + 1):
                if xin[k] - 0.5 <= px + 0.5 <= xin[k + 1] + 0.5:
                    cv.add(px, py, col, a)


def paint(cv, prims, s):
    """Lay down every primitive, each through the glow stack."""
    for wmul, amul in GLOW:
        for p in prims:
            t = p.get("t")
            a = float(p.get("a", 1.0)) * amul
            if a <= 0.002:
                continue
            col = hex2rgb(p.get("c", "#FFFFFF"))
            if t == "line":
                draw_line(cv, s, p["x1"], p["y1"], p["x2"], p["y2"],
                          float(p.get("w", 3)) * wmul, col, a)
            elif t == "circle":
                draw_ring(cv, s, p["cx"], p["cy"], p["r"],
                          float(p.get("w", 3)) * wmul, col, a)
            elif t == "disc":
                # A solid shape has no glow stack; draw it once, on the core pass.
                if wmul == 1.0:
                    draw_disc(cv, s, p["cx"], p["cy"],
                              p.get("rx", p.get("r", 3)),
                              p.get("ry", p.get("r", 3)), col, a)
            elif t == "poly":
                pts = p["pts"]
                if p.get("fill") and wmul == 1.0:
                    draw_fill(cv, s, pts, hex2rgb(p["fill"]),
                              float(p.get("fa", 0.25)))
                w = float(p.get("w", 3)) * wmul
                rng = range(len(pts)) if p.get("close") else range(len(pts) - 1)
                for i in rng:
                    ax, ay = pts[i]
                    bx, by = pts[(i + 1) % len(pts)]
                    draw_line(cv, s, ax, ay, bx, by, w, col, a)


def downsample(cv, out_n):
    """Box-average the SS grid down to the target size."""
    n, k = cv.n, SS
    out = bytearray(out_n * out_n * 4)
    inv = 1.0 / (k * k)
    for y in range(out_n):
        for x in range(out_n):
            r = g = b = a = 0.0
            for j in range(k):
                row = (y * k + j) * n + x * k
                for i in range(k):
                    q = row + i
                    r += cv.r[q]; g += cv.g[q]; b += cv.b[q]; a += cv.a[q]
            o = (y * out_n + x) * 4
            out[o] = min(255, int(r * inv * 255 + 0.5))
            out[o + 1] = min(255, int(g * inv * 255 + 0.5))
            out[o + 2] = min(255, int(b * inv * 255 + 0.5))
            out[o + 3] = min(255, int(a * inv * 255 + 0.5))
    return out


def write_png(path, rgba, n):
    raw = bytearray()
    stride = n * 4
    for y in range(n):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(t, d):
        return (struct.pack(">I", len(d)) + t + d +
                struct.pack(">I", zlib.crc32(t + d) & 0xffffffff))

    png = (b"\x89PNG\r\n\x1a\n" +
           chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
           chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)


def flatten_over_bg(rgba, n):
    """Composite the additive art over the deep-purple launcher background."""
    out = bytearray(rgba)
    br, bg_, bb = BG
    for i in range(0, len(out), 4):
        out[i] = min(255, br + out[i])
        out[i + 1] = min(255, bg_ + out[i + 1])
        out[i + 2] = min(255, bb + out[i + 2])
        out[i + 3] = 255
    return out


def render(prims, n):
    cv = Canvas(n * SS)
    paint(cv, prims, (n * SS) / VIEW)
    return downsample(cv, n)


# ---------------------------------------------------------------- vector XML

def _f(v):
    return ("%.2f" % float(v)).rstrip("0").rstrip(".")


def to_vector_xml(prims):
    """Same primitives as an Android vector drawable, so the adaptive icon
    stays crisp at any density instead of relying on the rasters."""
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           "<!--",
           "  x3circus launcher mark: BOTH CLOWNS ON THE SEESAW.",
           "",
           "  GENERATED BY tools/make_icon.py FROM tools/icon_spec.json.",
           "  Edit the spec and re-run; do not hand-edit this file.",
           "",
           "  108dp viewport, safe zone the middle 66dp.",
           "-->",
           '<vector xmlns:android="http://schemas.android.com/apk/res/android"',
           '    android:width="108dp"',
           '    android:height="108dp"',
           '    android:viewportWidth="108"',
           '    android:viewportHeight="108">',
           ""]

    def path(d, stroke=None, w=None, a=1.0, fill=None, fa=1.0, cap="round"):
        out.append("    <path")
        out.append('        android:pathData="%s"' % d)
        if fill:
            out.append('        android:fillColor="%s"' % fill)
            if fa < 0.999:
                out.append('        android:fillAlpha="%s"' % _f(fa))
        if stroke:
            out.append('        android:strokeColor="%s"' % stroke)
            out.append('        android:strokeWidth="%s"' % _f(w))
            out.append('        android:strokeLineCap="%s"' % cap)
            out.append('        android:strokeLineJoin="round"')
            if a < 0.999:
                out.append('        android:strokeAlpha="%s"' % _f(a))
        out.append("        />")

    for p in prims:
        t = p.get("t")
        a = float(p.get("a", 1.0))
        c = p.get("c", "#FFFFFF")
        if t == "line":
            path("M%s,%s L%s,%s" % (_f(p["x1"]), _f(p["y1"]),
                                    _f(p["x2"]), _f(p["y2"])),
                 stroke=c, w=p.get("w", 3), a=a)
        elif t == "circle":
            cx, cy, r = float(p["cx"]), float(p["cy"]), float(p["r"])
            d = ("M%s,%s a%s,%s 0 1,1 %s,0 a%s,%s 0 1,1 -%s,0" %
                 (_f(cx - r), _f(cy), _f(r), _f(r), _f(2 * r),
                  _f(r), _f(r), _f(2 * r)))
            path(d, stroke=c, w=p.get("w", 3), a=a)
        elif t == "disc":
            cx, cy = float(p["cx"]), float(p["cy"])
            rx = float(p.get("rx", p.get("r", 3)))
            ry = float(p.get("ry", p.get("r", 3)))
            d = ("M%s,%s a%s,%s 0 1,1 %s,0 a%s,%s 0 1,1 -%s,0" %
                 (_f(cx - rx), _f(cy), _f(rx), _f(ry), _f(2 * rx),
                  _f(rx), _f(ry), _f(2 * rx)))
            path(d, fill=c, fa=a)
        elif t == "poly":
            pts = p["pts"]
            d = "M%s,%s " % (_f(pts[0][0]), _f(pts[0][1]))
            d += " ".join("L%s,%s" % (_f(x), _f(y)) for x, y in pts[1:])
            if p.get("close"):
                d += " Z"
            if p.get("fill"):
                path(d, fill=p["fill"], fa=float(p.get("fa", 0.25)))
            path(d, stroke=c, w=p.get("w", 3), a=a)

    out.append("</vector>")
    return "\n".join(out) + "\n"


def main():
    spec_path = sys.argv[1]
    res = "app/src/main/res"
    preview = None
    for i, a in enumerate(sys.argv):
        if a == "--out":
            res = sys.argv[i + 1]
        if a == "--preview":
            preview = sys.argv[i + 1]

    spec = json.load(open(spec_path))
    prims = spec["prims"] if isinstance(spec, dict) else spec

    if preview:
        for n in (48, 96, 192, 432):
            write_png(os.path.join(preview, "preview_%d.png" % n),
                      flatten_over_bg(render(prims, n), n), n)
            print("  preview_%d.png" % n)
        return

    for dens, n in FOREGR.items():
        write_png("%s/mipmap-%s/ic_launcher_fg.png" % (res, dens),
                  render(prims, n), n)
    for dens, n in LEGACY.items():
        write_png("%s/mipmap-%s/ic_launcher.png" % (res, dens),
                  flatten_over_bg(render(prims, n), n), n)
    with open("%s/drawable/ic_circus_foreground.xml" % res, "w") as f:
        f.write(to_vector_xml(prims))
    print("icon written: %d primitives -> 5 densities + vector" % len(prims))


if __name__ == "__main__":
    main()
