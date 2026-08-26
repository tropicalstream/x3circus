#!/usr/bin/env python3
"""
Generate assets/sfx/yaao.wav - the clown's launch scream, by formant synthesis.

WHY SYNTHESIS. There is no TTS here, and macOS `say` is not an option: Apple's
voices are not licensed for redistribution and this repo is GPL-3.0 on GitHub.
So the voice is built the way a vocoder builds one - a glottal source shaped by
resonant formant filters:

  SOURCE      A Rosenberg glottal pulse train at f0, with period jitter and
              amplitude shimmer. A plain impulse train sounds like a buzzer;
              the asymmetric open/close shape is most of what makes it read as
              a throat.
  FORMANTS    A CASCADE of five two-pole resonators. Cascade rather than
              parallel because for vowels it gets the relative formant
              amplitudes right for free, which is exactly the thing that is
              fiddly to hand-tune in a parallel bank.
  RADIATION   A first difference at the output, which is what lips do to
              glottal flow - and it is also why the result is not bass-heavy,
              which suits a device whose speakers have no bass anyway.

The formants GLIDE between segments. A scream that holds one fixed vowel sounds
like a test tone; the movement is what makes it a voice saying "yaaaaaao"
instead of a filter sweep.

Pitched deliberately high (f0 in the 250-600 Hz range, not a chest-voice 110)
so the harmonics land in the 0.8-4 kHz band the X3's small speakers can
actually reproduce - the same constraint that shaped the balloon pop.

Usage:  make_scream.py [spec.json] [-o out.wav]
"""

import json
import math
import os
import random
import struct
import sys

SR = 22050


def lerp_track(track, t, key, default):
    """Linear interpolation over a list of {tMs/startMs: ..., key: ...}."""
    if not track:
        return default
    tk = "tMs" if "tMs" in track[0] else "startMs"
    if t <= track[0][tk]:
        return track[0][key]
    for a, b in zip(track, track[1:]):
        if a[tk] <= t <= b[tk]:
            span = b[tk] - a[tk]
            if span <= 0:
                return b[key]
            u = (t - a[tk]) / span
            return a[key] + (b[key] - a[key]) * u
    return track[-1][key]


class Reson:
    """Two-pole resonator. Gain normalised so the cascade keeps a flat level."""

    def __init__(self):
        self.y1 = self.y2 = 0.0

    def step(self, x, f, bw):
        r = math.exp(-math.pi * bw / SR)
        th = 2 * math.pi * f / SR
        b = 2 * r * math.cos(th)
        c = -r * r
        a = 1.0 - b - c
        y = a * x + b * self.y1 + c * self.y2
        self.y2, self.y1 = self.y1, y
        return y


def synth(spec, seed=3):
    rnd = random.Random(seed)
    dur = spec["durationMs"] / 1000.0
    n = int(SR * dur)
    segs = sorted(spec["segments"], key=lambda s: s["startMs"])
    pitch = sorted(spec["pitch"], key=lambda p: p["tMs"])
    env = sorted(spec.get("ampEnvelope") or [], key=lambda p: p["tMs"])
    vr = spec.get("vibratoRateHz", 5.5)
    vd = spec.get("vibratoDepthCents", 40.0)
    breath = spec.get("breathiness", 0.10)

    res = [Reson() for _ in range(5)]
    # Bandwidths widen with formant number, as they do in a real tract.
    BW = [80.0, 100.0, 150.0, 260.0, 350.0]

    out = [0.0] * n
    phase = 0.0          # 0..1 within the current glottal period
    period_jit = 1.0
    shimmer = 1.0
    prev = 0.0

    for i in range(n):
        t = i / SR
        tms = t * 1000.0

        f0 = lerp_track(pitch, tms, "f0", 300.0)
        f0 *= 2 ** ((math.sin(2 * math.pi * vr * t) * vd) / 1200.0)
        f0 = max(60.0, f0)

        # --- glottal source ------------------------------------------------
        phase += f0 * period_jit / SR
        if phase >= 1.0:
            phase -= 1.0
            # A little irregularity every cycle. Perfectly periodic is robotic.
            period_jit = 1.0 + rnd.uniform(-0.012, 0.012)
            shimmer = 1.0 + rnd.uniform(-0.07, 0.07)
        # Rosenberg pulse: slow opening, faster closing.
        T1, T2 = 0.40, 0.16
        if phase < T1:
            g = 0.5 * (1.0 - math.cos(math.pi * phase / T1))
        elif phase < T1 + T2:
            g = math.cos(math.pi * (phase - T1) / (2 * T2))
        else:
            g = 0.0
        g *= shimmer
        # Breath noise, gated by the open phase so it belongs to the voice.
        if breath > 0.0:
            g += rnd.uniform(-1, 1) * breath * (1.0 if phase < T1 + T2 else 0.25)

        # --- vocal tract ---------------------------------------------------
        f1 = lerp_track(segs, tms, "f1", 700.0)
        f2 = lerp_track(segs, tms, "f2", 1100.0)
        f3 = lerp_track(segs, tms, "f3", 2500.0)
        amp = lerp_track(segs, tms, "amp", 1.0)
        x = g
        for k, f in enumerate((f1, f2, f3, 3300.0, 4500.0)):
            x = res[k].step(x, min(f, SR * 0.45), BW[k])

        # --- lip radiation (first difference) ------------------------------
        y = x - 0.96 * prev
        prev = x

        gain = lerp_track(env, tms, "gain", 1.0) if env else 1.0
        out[i] = y * amp * gain

    peak = max(abs(v) for v in out) or 1.0
    out = [v / peak * 0.94 for v in out]
    # Clean edges so the mixer never clicks.
    ramp = int(0.004 * SR)
    for k in range(ramp):
        out[k] *= k / ramp
        out[n - 1 - k] *= k / ramp
    return out


def write_wav(path, s):
    data = b"".join(struct.pack("<h", max(-32768, min(32767, int(v * 32767))))
                    for v in s)
    hdr = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " +
           struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16) +
           b"data" + struct.pack("<I", len(data)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(hdr + data)


# The house design, used when no spec file is given: a yelp up as he leaves the
# plank, a long wobbling "aaaa" over the top of the arc, and a slide down into
# "ao" as gravity takes him back. The terminal fall is the joke.
HOUSE = {
    "name": "yaaaaaao",
    # A yelp up off the plank, a wobbling "aaaa" over the top of the arc, and a
    # long slide down into "ao" as gravity takes him back. The terminal fall is
    # the joke, so it gets 45% of the duration.
    #
    # TWO THINGS HERE ARE NOT TASTE, THEY ARE ACOUSTICS:
    #
    # 1. F2 NEVER DROPS BELOW ~980 Hz, not even in the tail. The natural way to
    #    round /a/ -> /o/ -> /u/ walks F1 down to ~350 and F2 to ~800, and on
    #    this device that is silence: the fall-away gesture ends up written
    #    entirely into the band the X3's speakers cannot reproduce, so the
    #    punchline simply stops at 900 ms. The rounding is carried by F1 and by
    #    f0 instead, and F2 stays in-band the whole way down.
    #
    # 2. f0 SITS NEAR 370-415 IN THE SUSTAIN so that its SECOND HARMONIC lands
    #    on F1 (~740). Screaming this at 550-620 Hz - the obvious choice for a
    #    comic yelp - puts F1 in the gap between H1 and H2 where no harmonic
    #    excites it, and a formant nothing excites is not a vowel: it collapses
    #    into a pitched soprano whistle. Sparse harmonics are the whole
    #    difficulty of high-pitched formant synthesis.
    "durationMs": 1150,
    "segments": [
        {"phoneme": "j", "startMs": 0,    "f1": 330, "f2": 2100, "f3": 2900, "amp": 0.60},
        {"phoneme": "a", "startMs": 85,   "f1": 780, "f2": 1350, "f3": 2550, "amp": 1.00},
        {"phoneme": "a", "startMs": 270,  "f1": 745, "f2": 1180, "f3": 2470, "amp": 0.95},
        {"phoneme": "A", "startMs": 620,  "f1": 620, "f2": 1060, "f3": 2430, "amp": 0.88},
        {"phoneme": "o", "startMs": 830,  "f1": 500, "f2": 1010, "f3": 2500, "amp": 0.78},
        {"phoneme": "o", "startMs": 1150, "f1": 460, "f2": 980,  "f3": 2450, "amp": 0.58},
    ],
    "pitch": [
        {"tMs": 0, "f0": 300}, {"tMs": 85, "f0": 470}, {"tMs": 190, "f0": 510},
        {"tMs": 300, "f0": 395}, {"tMs": 430, "f0": 415}, {"tMs": 560, "f0": 385},
        {"tMs": 700, "f0": 370}, {"tMs": 850, "f0": 340}, {"tMs": 1000, "f0": 315},
        {"tMs": 1150, "f0": 290},
    ],
    "vibratoRateHz": 6.5,
    "vibratoDepthCents": 55,
    "breathiness": 0.18,
    "ampEnvelope": [
        {"tMs": 0, "gain": 0.0},   {"tMs": 30, "gain": 0.90},
        {"tMs": 90, "gain": 0.75}, {"tMs": 200, "gain": 1.0},
        {"tMs": 350, "gain": 0.90}, {"tMs": 600, "gain": 0.86},
        {"tMs": 800, "gain": 0.80}, {"tMs": 1000, "gain": 0.62},
        {"tMs": 1150, "gain": 0.0},
    ],
}


def stats(s, label):
    n = len(s)
    peak = max(abs(v) for v in s)
    rms = math.sqrt(sum(v * v for v in s) / n)
    print("  %-20s %5.0f ms  peak %.2f  rms %.3f  crest %4.1f dB"
          % (label, n / SR * 1000, peak, rms,
             20 * math.log10(peak / rms) if rms else 0))


if __name__ == "__main__":
    out = "/Users/me/Projects/x3circus/app/src/main/assets/sfx/yaao.wav"
    spec = HOUSE
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "-o":
            out = args[i + 1]
        elif not a.startswith("-") and (i == 0 or args[i - 1] != "-o"):
            spec = json.load(open(a))
    s = synth(spec)
    write_wav(out, s)
    print("wrote %s" % out)
    stats(s, spec.get("name", "scream"))
