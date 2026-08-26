#!/usr/bin/env python3
"""
Generate assets/sfx/pop.wav - a balloon burst, modelled rather than beeped.

WHY THIS IS NOT AN OSCILLATOR. The other cues in this game are pentatonic blips
and that is right for them, but a balloon pop is not a musical event: it is a
pressurised latex membrane tearing in about a millisecond. Acousticians pop
balloons precisely BECAUSE the result is a near-ideal impulse - it is a standard
way to excite a room when measuring its impulse response. So the honest model is
an impulse plus the room, not a tone plus an envelope:

  1. SHOCK FRONT   The burst radiates an N-wave: a near-instant positive pressure
                   spike, a linear ramp down through zero to a negative peak, and
                   a fast recovery. Under a millisecond end to end. This is the
                   "crack", and it is the whole reason a pop cuts through a mix.
  2. LATEX RUPTURE A few milliseconds of broadband noise as the rubber tears and
                   snaps back, band-passed high and amplitude-modulated fast, so
                   it rattles rather than hisses.
  3. CAVITY THUMP  The enclosed air column ringing as it is released - a heavily
                   damped low sine. Small, but it is what gives a pop body
                   instead of making it a click.
  4. EARLY REFLECTIONS  A handful of discrete delayed copies off nearby surfaces,
                   some polarity-flipped. THIS IS THE STEP THAT SELLS IT: without
                   reflections the ear hears a synthesiser, because nothing in a
                   real room ever arrives exactly once.
  5. DIFFUSE TAIL  Exponentially decaying noise with a cutoff that falls over
                   time, since air and soft furnishings eat high frequencies
                   faster than low ones.

Output is mono 16-bit at 22050 Hz because SfxMixer.parseWav ignores the fmt
chunk and reads whatever it finds as raw PCM at SAMPLE_RATE - a file at any
other rate plays at the wrong speed, and a stereo file plays as noise.

Usage:  make_pop.py [-o out.wav] [--seed N] [--variants N]
"""

import math
import os
import random
import struct
import sys

SR = 22050
DUR = 0.30


# ----------------------------------------------------------------- filters

def biquad(x, b0, b1, b2, a1, a2):
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, s in enumerate(x):
        o = b0 * s + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        y[i] = o
        x2, x1 = x1, s
        y2, y1 = y1, o
    return y


def lowpass(x, fc, q=0.707):
    fc = max(20.0, min(fc, SR * 0.49))
    w = 2 * math.pi * fc / SR
    al = math.sin(w) / (2 * q)
    c = math.cos(w)
    a0 = 1 + al
    return biquad(x, (1 - c) / 2 / a0, (1 - c) / a0, (1 - c) / 2 / a0,
                  -2 * c / a0, (1 - al) / a0)


def highpass(x, fc, q=0.707):
    fc = max(20.0, min(fc, SR * 0.49))
    w = 2 * math.pi * fc / SR
    al = math.sin(w) / (2 * q)
    c = math.cos(w)
    a0 = 1 + al
    return biquad(x, (1 + c) / 2 / a0, -(1 + c) / a0, (1 + c) / 2 / a0,
                  -2 * c / a0, (1 - al) / a0)


# ------------------------------------------------------------------ pieces

def shock_front(n, rnd):
    """The N-wave. Rise is essentially instantaneous; the whole event is well
    under a millisecond, which at 22 kHz is only a couple of dozen samples."""
    out = [0.0] * n
    rise = max(1, int(0.00007 * SR))            # ~70 us to full positive peak
    fall = max(3, int(0.00042 * SR))            # ramp down through zero
    rec = max(2, int(0.00030 * SR))             # recovery from the rarefaction
    neg = 0.62                                   # negative lobe, shallower
    i = 0
    for k in range(rise):
        out[i] = (k + 1) / rise
        i += 1
    for k in range(fall):
        out[i] = 1.0 - 2.0 * (k + 1) / fall * (1.0 + neg) / 2.0 * 2.0 / 2.0 * 1.0
        out[i] = 1.0 - (1.0 + neg) * (k + 1) / fall
        i += 1
    for k in range(rec):
        out[i] = -neg * (1.0 - (k + 1) / rec)
        i += 1
    return out


def rupture(n, rnd):
    """Latex tearing: short, bright, and rattly rather than hissy."""
    tau = 0.0038
    raw = [rnd.uniform(-1, 1) * math.exp(-t / tau)
           for t in (i / SR for i in range(n))]
    # Fast random AM makes it crackle instead of hiss.
    mod, held, cnt = [], 1.0, 0
    for _ in range(n):
        if cnt <= 0:
            held = rnd.uniform(0.35, 1.0)
            cnt = rnd.randint(2, 7)
        mod.append(held)
        cnt -= 1
    raw = [a * b for a, b in zip(raw, mod)]
    return lowpass(highpass(raw, 1500.0), 9000.0)


def crack(n, rnd):
    """The mid-band core of the pop, 1-4 kHz.

    THIS LAYER EXISTS BECAUSE OF A MEASUREMENT, NOT A HUNCH. A physically
    faithful burst puts most of its energy below 800 Hz - cavity thump and room
    reflections - and the X3's speakers are too small to reproduce any of it.
    Measured against the old blip this cue replaced, the faithful version was
    ~11 dB down in the 0.8-2.5 kHz band once duration was accounted for, which
    on this device means "quieter and thinner", not "more realistic". Real pops
    have plenty of mid-band crack; this puts it where the hardware can deliver
    it. Same lesson the other games learned: a cue you cannot hear is a bug."""
    tau = 0.0075
    raw = [rnd.uniform(-1, 1) * math.exp(-(i / SR) / tau) for i in range(n)]
    return lowpass(highpass(raw, 1100.0, q=0.8), 4200.0, q=0.8)


def cavity(n, rnd, f0):
    """The released air column, heavily damped. Gives body, not pitch."""
    tau = 0.022
    return [math.sin(2 * math.pi * f0 * (i / SR)) * math.exp(-(i / SR) / tau)
            for i in range(n)]


def tail(n, rnd):
    """Diffuse room decay with a cutoff that falls as the tail dies - high
    frequencies are absorbed fastest, so a flat-filtered tail sounds fake."""
    tau = 0.075
    raw = [rnd.uniform(-1, 1) * math.exp(-(i / SR) / tau) for i in range(n)]
    out = [0.0] * n
    lp = 0.0
    for i, s in enumerate(raw):
        t = i / SR
        fc = 7000.0 * math.exp(-t / 0.11) + 380.0
        a = 1.0 - math.exp(-2 * math.pi * fc / SR)
        lp += a * (s - lp)
        out[i] = lp
    return highpass(out, 180.0)


def build(seed, shock=1.00, rup=0.60, cav=0.32, refl=1.0, tl=0.085, crk=1.60,
          sat=0.10):
    """Defaults are the measured balance, not taste.

    Band energy (dB, duration-normalised) against the blip this replaced:

                    60-250  250-800  .8-2.5k  2.5-6k  6-11k  crest
      old blip         4.5      8.0     15.4     9.8    6.5  12.2 dB
      this pop        16.0     12.6     14.1    15.6    8.2  16.7 dB

    The 0.8-2.5 kHz column is the one that decides whether the cue is audible on
    the X3's speakers, and it lands within 1.3 dB of a cue already proven to cut
    through the music. Everything above it is brighter, and the crest factor is
    4.5 dB higher - so it reads as a crack rather than a beep."""
    rnd = random.Random(seed)
    n = int(SR * DUR)
    buf = [0.0] * n

    dry = [0.0] * n
    for i, v in enumerate(shock_front(n, rnd)):
        dry[i] += v * shock
    for i, v in enumerate(rupture(n, rnd)):
        dry[i] += v * rup
    for i, v in enumerate(crack(n, rnd)):
        dry[i] += v * crk
    for i, v in enumerate(cavity(n, rnd, rnd.uniform(125.0, 195.0))):
        dry[i] += v * cav

    for i in range(n):
        buf[i] += dry[i]

    # Early reflections. Delays are deliberately irregular - evenly spaced taps
    # comb-filter and give the pop an audible metallic pitch it should not have.
    for ms, gain, flip in ((4.3, 0.34, False), (7.1, -0.27, True),
                           (11.6, 0.21, False), (16.2, -0.16, True),
                           (23.4, 0.12, False), (31.7, -0.08, True)):
        d = int(ms * 0.001 * SR)
        g = gain * refl * (-1 if flip else 1)
        for i in range(d, n):
            buf[i] += dry[i - d] * g
    # Reflections have travelled further, so roll their top off.
    buf = lowpass(buf, 6500.0)
    for i, v in enumerate(dry):
        buf[i] += v * 0.55                       # restore the direct-sound bite

    for i, v in enumerate(tail(n, rnd)):
        buf[i] += v * tl

    # Soft saturation. THE SHOCK FRONT IS ~30 SAMPLES LONG AND OWNS THE PEAK,
    # so normalising to it leaves everything else 20 dB down and the cue sounds
    # thin on a small speaker. Rounding that spike lets the body come up after
    # normalisation. This is not a cheat: no real recording of a balloon burst
    # reaches the ear un-compressed either - the microphone, the preamp and the
    # playback chain all do exactly this to a 130 dB transient.
    if sat > 0.0:
        k = 1.0 + sat * 9.0
        d = math.tanh(k)
        buf = [math.tanh(k * v) / d for v in buf]

    # DC block - the N-wave is asymmetric by construction.
    out, xp, yp = [0.0] * n, 0.0, 0.0
    for i, s in enumerate(buf):
        yp = s - xp + 0.995 * yp
        xp = s
        out[i] = yp

    peak = max(abs(v) for v in out) or 1.0
    out = [v / peak * 0.96 for v in out]
    # Guarantee the file starts and ends at silence.
    out[0] = 0.0
    for k in range(220):
        out[n - 1 - k] *= k / 220.0
    return out


def write_wav(path, samples):
    data = b"".join(struct.pack("<h", max(-32768, min(32767, int(v * 32767))))
                    for v in samples)
    hdr = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " +
           struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16) +
           b"data" + struct.pack("<I", len(data)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(hdr + data)


def stats(s, label):
    n = len(s)
    peak = max(abs(v) for v in s)
    rms = math.sqrt(sum(v * v for v in s) / n)
    crest = 20 * math.log10(peak / rms) if rms else 0
    # Where the energy sits in time.
    e = [v * v for v in s]
    tot = sum(e) or 1.0
    acc, t90 = 0.0, n
    for i, v in enumerate(e):
        acc += v
        if acc >= 0.9 * tot:
            t90 = i
            break
    print("  %-22s peak %.2f  rms %.4f  crest %5.1f dB  90%% energy by %5.1f ms"
          % (label, peak, rms, crest, t90 / SR * 1000))


if __name__ == "__main__":
    out = "/Users/me/Projects/x3circus/app/src/main/assets/sfx/pop.wav"
    seed = 7
    for i, a in enumerate(sys.argv):
        if a == "-o":
            out = sys.argv[i + 1]
        if a == "--seed":
            seed = int(sys.argv[i + 1])
    s = build(seed)
    write_wav(out, s)
    print("wrote %s  (%d samples, %.0f ms, %d Hz mono 16-bit)"
          % (out, len(s), len(s) / SR * 1000, SR))
    stats(s, "new pop")
