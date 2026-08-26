# x3circus — the 1977 seesaw game, played for laughs

Free software, GPL v3 (see LICENSE). Derived from `x3breakout`, which is GPL v3.

A clown falls. You slide a seesaw under him. He lands on one end, which flings
the *other* clown up into the balloons. Miss, and he finds the sawdust.

## Controls

| gesture | |
|---|---|
| **drag** | slide the seesaw |
| **tap** | **HONK** — and it nudges the clown mid-flight |
| BACK | leave the big top |

Nothing is bound to a double tap. Nothing to a long press either: on this
hardware the launcher owns it, and holding still opens the system control panel
over the game.

## Made easier than 1977, on purpose

The original Circus is a good game and a brutal one — small seesaw, fast clown,
instant miss. The brief was hilarious and not too difficult, so:

- The seesaw is **wide** and the catch window is generous (±0.155 either side of
  the end, against a clown a third that size).
- **The honk steers.** Tapping shoves the airborne clown toward wherever the
  seesaw currently is, so one control does both jobs and a miss you can see
  coming is a miss you had a chance to fix. It is the silliest possible steering
  mechanism, which is why it is in.
- A miss costs a life but the act continues, with a remark.
- Difficulty ramps by **gravity alone** — flights get shorter, nothing else
  changes. **GRAVITY: FORGIVING** on the menu softens even that.

Score comes from **streaks inside a single flight**, so a good launch pays
better than grinding.

## The soundtrack

Three calliope galops in `assets/music`, **composed for this game** rather than
sourced. The public-domain circus marches everyone thinks of — Fučík's *Entrance
of the Gladiators* (1897), Sousa's marches of the 1890s — are unambiguously
public domain as **compositions**, but a specific *recording* of one carries its
own separate rights, and verifying that per-upload was more risk than it was
worth for a game that only needs a minute of music.

So these are written in the idiom instead: oom-pah bass under square-wave
melody, chromatic descents, and a pitch that **wanders on purpose**. A real
calliope is a boiler with a keyboard bolted to it and never quite holds a note —
the wobble is the joke, and it costs 484 KB for the whole soundtrack instead of
the 17–26 MB the other games carry.

Sound effects are generated too: the boing overshoots and wobbles back like a
spring, the honk is two pitches a semitone apart (which is what makes a horn
sound rude), and the splat is over quickly because comedy failure should not
sound like tragedy.

## Icon

Both clowns on the seesaw, drawn from the game's own art: `tools/icon_spec_build.py`
transcribes `drawClown` feature by feature, every size the same multiple of `r`
the game uses, so the launcher mark is the same character the player sees rather
than a lookalike redrawn by eye. `tools/make_icon.py` rasterises it to all five
densities plus the adaptive-icon vector. Both are dependency-free - this machine
has no PIL, no cairo and no SVG rasteriser - so regenerating the icon is:

```
python3 tools/icon_spec_build.py && python3 tools/make_icon.py tools/icon_spec.json
```

An earlier icon was a tent and three balloons, on the reasoning that a clown's
face is unreadable at 48 dp. That was half right, and the half that was wrong is
worth writing down:

- **The clown has to be BIG.** At `r=6` each head lands on about 6 px at 48 dp
  and every feature that says "clown" is sub-pixel; the figures collapse into
  blobs and only the hats survive. `r=9` is the floor, and it costs plank length,
  which is why the plank is short and steeply tilted rather than spanning the
  viewport.
- **Then it has to be SIMPLIFIED.** The game stacks a head outline, a head fill,
  three hair tufts a side and a collar all within 2r, which at icon scale merge
  into one pink halo with no head in it. The icon drops the fill, keeps one tuft
  a side, and pushes the collar down and wider so it reads as under the head.
- **Additive blending blows the figures out.** The game gets away with summing
  light because its strokes are far apart. Here a clown's features sit 1-4 units
  apart under a 7-unit glow, every overlap piles up, and the whole figure
  saturates to white. `make_icon.py` composites with SCREEN, which rolls off
  instead of clipping and keeps the hues.
- **Limbs need their own hue.** The game's cyan arms sit one step from the
  plank's `#66E6FF`; at icon size they merged with it and read as the clown
  holding a pole. They are `#9CFFC4` here, short and steep.

The auto-fitter in `icon_spec_build.py` scales the finished composition to fill
the adaptive-icon safe zone, so the art is as large as the mask allows instead
of floating in dead space. Design in whatever coordinates are comfortable and
let it fit.

## The lever

Where the clown lands on the plank is the whole skill of the game. Torque is
force times distance from the pivot, so `power = armIn / END` — how far out he
struck, over the distance to the other clown standing at the end.

**Apex is LINEAR in power, not quadratic.** Torque times distance is work, work
is energy, and energy is height, so mechanical advantage buys apex directly.
Driving the launch *velocity* with power instead made apex go as power squared,
and the top of the range simply slammed into the tent roof — measured on device,
a 1.36 catch and a 1.68 catch both apexed at 1.03 and looked identical. The
reward for hitting the tip was invisible. `apexVy()` now solves `v = sqrt(2gh)`
for a target apex of `APEX_BASE + APEX_GAIN * power`, which also means a heavier
later act shortens the HANG TIME rather than flattening the arc — the balloon
rows are at fixed heights and have to stay reachable however many laps deep the
player is.

The constants are tuned so each tier of catch unlocks one more row. Measured on
device, balloon rows at 0.60 / 0.74 / 0.88 and the roof at 1.02:

| catch | landOut | power | apex | reaches |
|---|---|---|---|---|
| well inboard | −0.50 | 0.70 | 0.58 | row 0 |
| square on the end | 0.00 | 1.00 | 0.76 | rows 0–1 |
| edging outboard | +0.31 | 1.23 | 0.89 | **rows 0–2** |
| near the edge | +0.63 | 1.45 | 0.99 | rows 0–2 |
| on the tip | +1.00 | 1.73 | 1.02 | **bounces off the big top** |

**The slope is set by where the top row is, not by taste.** An earlier
0.34 + 0.38p curve needed a catch past landOut +0.4 before it reached row 2 at
all, and even then it apexed at 0.88 — the row's own height, grazing it with no
margin. Landing near the edge is the payoff of the whole game, so the curve
pivots about the weak end and lifts the strong end until landing just 19%
outboard of the plank end reaches the upper balloons, while a square catch still
tops out at row 1. The biggest launches now exceed the roof and bounce off the
canvas: there is nowhere above 1.02 to go anyway, so making them visibly and
audibly hit the tent turns a silent clamp into the loudest available "that was a
big one".

**`END` is shared by the rules and the renderer and must stay that way.** The
model had the plank ends at 0.13 while the renderer drew the plank at 0.24 and
the target marker at 0.22 — so the spot the player aimed at was nowhere near the
spot the lever arithmetic measured from. `Game.kt` derives the plank half-width
and the marker from `END * HALF_W` for that reason.

Read the landing position BEFORE moving `flyX` to the launch point. Computing
the sideways term afterwards makes `(flyX - end)` a fixed `2*END`, which
saturates the ratio at ±1 on every single catch and quietly turns a
position-dependent throw into a constant.

## The balloon pop

`tools/make_pop.py`. The other cues in this game are pentatonic blips and that is
right for them, but a balloon pop is not a musical event - it is a pressurised
latex membrane tearing in about a millisecond. Acousticians pop balloons
precisely BECAUSE the result is a near-ideal impulse; it is a standard way to
excite a room when measuring its response. So the model is an impulse plus a
room, not a tone plus an envelope: an N-wave shock front, a few milliseconds of
band-passed latex rupture, a damped cavity thump, six irregularly spaced early
reflections, and a diffuse tail whose cutoff falls as it decays.

**The faithful version was the wrong answer, and only a measurement showed it.**
Band energy, duration-normalised, against the 50 ms blip it replaced:

| | 60-250 | 250-800 | 0.8-2.5k | 2.5-6k | 6-11k | crest |
|---|---|---|---|---|---|---|
| old blip | 4.5 | 8.0 | **15.4** | 9.8 | 6.5 | 12.2 dB |
| faithful model | 14.1 | 9.9 | **4.4** | 2.1 | -1.7 | 27.3 dB |
| shipped | 16.0 | 12.6 | **14.1** | 15.6 | 8.2 | 16.7 dB |

A physically honest burst puts most of its energy below 800 Hz, in cavity thump
and room reflections, and the X3's speakers cannot reproduce any of it - the
faithful version was 11 dB down in the one band that decides audibility. Two
things fixed it without turning it back into a beep: a dedicated 1-4 kHz crack
layer, and gentle soft-saturation. The saturation is not a cheat. The shock front
is about 30 samples long and owns the peak, so normalising to it leaves
everything else 20 dB down; no real recording of a balloon burst reaches the ear
un-compressed either, since the microphone, preamp and playback chain all do
exactly this to a 130 dB transient. The result matches a cue already proven to
cut through the music, is 6 dB brighter above it, and keeps 4.5 dB more crest -
so it reads as a crack, not a blip.

Pops are **pitched per balloon** in `Game.kt`: higher rows read as the smaller
balloons and a smaller balloon pops higher, plus jitter, so a streak does not
sound like one sample on repeat.

Anything added to `assets/sfx/` must be **mono 16-bit at 22050 Hz**.
`SfxMixer.parseWav` ignores the fmt chunk and reads whatever it finds as raw PCM
at `SAMPLE_RATE`, so a file at another rate plays at the wrong speed and a stereo
file plays as noise.

## The scream

`tools/make_scream.py`, triggered above lever power 1.25 — comfortably past the
1.13 that first reaches the top row, so it means "this one is going all the way
up" rather than firing on every decent catch.

There is no TTS here, and macOS `say` is not an option: Apple's voices are not
licensed for redistribution and this repo is GPL-3.0. So the voice is built the
way a vocoder builds one — a Rosenberg glottal pulse train with period jitter and
shimmer, through a **cascade** of five two-pole formant resonators, with a first
difference at the output for lip radiation. Formants glide between segments; a
scream holding one fixed vowel is a test tone, and the movement is most of what
makes it read as a voice.

Two constants in there are acoustics, not taste:

- **F2 never drops below ~980 Hz, even in the tail.** Rounding /a/ → /o/ → /u/
  naturally walks F1 down to ~350 and F2 to ~800, and on this device that is
  silence — the fall-away gesture ends up written entirely into the band the X3
  cannot reproduce, so the punchline just stops at 900 ms. The rounding is
  carried by F1 and f0 instead while F2 stays in-band the whole way down.
- **f0 sits near 370–415 in the sustain so its second harmonic lands on F1
  (~740).** Screaming this at 550–620 Hz — the obvious choice for a comic yelp —
  puts F1 in the gap between H1 and H2 where no harmonic excites it, and a
  formant nothing excites is not a vowel: it collapses into a pitched soprano
  whistle. Sparse harmonics are the whole difficulty of high-pitched formant
  synthesis.

## Build

```
./gradlew :app:assembleDebug
adb -s <glasses-serial> install -r app/build/outputs/apk/debug/x3circus.apk
```

## Device notes

- **Long press belongs to the OS.** Do not design a gesture around it.
- The launcher **force-stops the app** when it loses foreground; `onDestroy`
  never arrives, so save in `onPause`.
- Visible field ≈ **±0.144 across, ±0.117 up** in plane-local metres; the vector
  font advances ~5.4× its size parameter per character and stands ~7.3× tall.
- **If nothing appears, check `batch.setBasis(...)` is still called in
  `Game.update`.**
