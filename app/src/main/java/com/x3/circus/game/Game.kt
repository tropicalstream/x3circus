package com.x3.circus.game

import com.x3.circus.Settings
import com.x3.circus.audio.GameAudio
import com.x3.circus.input.SwipeControl
import com.x3.circus.render.NeonBatch
import com.x3.circus.render.Particles
import com.x3.circus.render.VectorFont
import kotlin.math.cos
import kotlin.random.Random
import kotlin.math.sin

/**
 * ============================================================================
 *  CIRCUS — the 1977 seesaw game, played for laughs.
 * ============================================================================
 *
 *     drag   slide the seesaw
 *     tap    HONK (and nudge the clown mid-flight)
 *
 * Nothing is bound to a double tap, and nothing to a long press — the launcher
 * owns that one on this hardware.
 *
 * The comedy is in the reactions, not in the rules: the clown pinwheels while
 * he flies, lands face-first when you miss, and the ringmaster has opinions.
 */
class Game(
    private val settings: Settings,
    private val audio: GameAudio,
    private val swipe: SwipeControl
) {

    val batch = NeonBatch()
    @JvmField var fps: Float = 0f
    @JvmField var tempC: Int = 0

    private companion object {
        const val ISO_TILT = 0.16f
        const val HALF_W = 0.1250f
        const val BOT_V = -0.1000f
        const val TOP_V = 0.1050f

        const val ST_MENU = 0
        const val ST_PLAY = 1
        const val ST_ACT = 2
        const val ST_OVER = 3
        const val ROW_GAP_MS = 150L

        /** Half the usable width, measured on the device. */
        const val EDGE = 0.138f
    }

    private val circus = Circus()
    private val parts = Particles(512)

    private var state = ST_MENU
    private var stateT = 0f
    private var row = 1
    private var lastRowMs = 0L
    private var actNo = 1
    private var act = Acts.get(1)
    private var musicPlaying = -1
    private var shake = 0f

    /** A quip on screen, and how long it has left. */
    private var quip = ""
    private var quipT = 0f

    private val events = ArrayList<Char>(8)
    private val windowScales = floatArrayOf(70f, 92f, 115f)

    /** Balloon colours, one per row, all loud. */
    private val rowR = floatArrayOf(1.00f, 1.00f, 0.35f)
    private val rowG = floatArrayOf(0.35f, 0.85f, 0.75f)
    private val rowB = floatArrayOf(0.55f, 0.20f, 1.00f)

    private val missQuips = arrayOf(
        "OOF", "THE SAWDUST BROKE HIS FALL", "HE MEANT TO DO THAT",
        "STILL BILLED AS AN ACROBAT", "APPLAUSE ANYWAY", "PHYSICS: UNDEFEATED")
    private val streakQuips = arrayOf("NICE", "SHOWMAN", "THE CROWD GOES MILD", "UNSTOPPABLE")
    private var missIdx = 0
    private var streakIdx = 0

    init { parts.scaleLengths(0.013f) }

    fun tap() { synchronized(events) { events.add('T') } }
    fun doubleTap() { }
    fun swipe(steps: Int) { synchronized(events) { events.add(if (steps > 0) '+' else '-') } }

    private fun drainInput() {
        synchronized(events) {
            for (e in events) when (e) {
                '+' -> onSwipe(1); '-' -> onSwipe(-1); 'T' -> onTap()
            }
            events.clear()
        }
    }

    private fun onSwipe(dir: Int) {
        if (state != ST_MENU) return
        val now = android.os.SystemClock.uptimeMillis()
        if (now - lastRowMs < ROW_GAP_MS) return
        lastRowMs = now
        row = ((row + dir) % 2 + 2) % 2
        audio.sfx("ui")
    }

    private fun onTap() {
        when (state) {
            ST_MENU -> if (row == 0) { settings.relaxed = !settings.relaxed; audio.sfx("honk") } else startRun()
            ST_PLAY -> { circus.honk(); audio.sfx("honk") }
            ST_ACT -> startAct(actNo + 1, false)
            else -> { state = ST_MENU; stateT = 0f; row = 1; stopMusic(); audio.sfx("ui") }
        }
    }

    fun back(): Boolean = when (state) {
        ST_PLAY, ST_ACT -> { stopMusic(); state = ST_MENU; stateT = 0f; row = 1; true }
        ST_OVER -> { state = ST_MENU; stateT = 0f; row = 1; true }
        else -> false
    }

    private fun startRun() = startAct(1, true)

    private fun startAct(n: Int, fresh: Boolean) {
        actNo = n
        act = Acts.get(n)
        circus.startAct(
            if (settings.relaxed) Act(act.n, act.name, act.gravity * 0.86f, act.launch,
                act.music, act.quip) else act, fresh)
        parts.clear()
        state = ST_PLAY; stateT = 0f; shake = 0f
        quip = act.quip; quipT = 2.4f
        if (musicPlaying != act.music) { audio.playLevelMusic(act.music + 1); musicPlaying = act.music }
        audio.sfx("drum")
    }

    private fun stopMusic() { if (musicPlaying >= 0) { audio.stopLevelMusic(); musicPlaying = -1 } }

    fun update(dt: Float) {
        stateT += dt
        drainInput()
        if (state == ST_PLAY) { circus.moveTo(swipe.pos01 * 2f - 1f); step(dt) }
        parts.update(dt)
        if (shake > 0f) shake = (shake - dt * 2.4f).coerceAtLeast(0f)
        if (quipT > 0f) quipT = (quipT - dt).coerceAtLeast(0f)

        val s = windowScales[settings.windowSize.coerceIn(0, 2)]
        val ct = cos(ISO_TILT); val st = sin(ISO_TILT)
        batch.setBasis(0f, 0f, 0f, s, 0f, 0f, 0f, s * ct, -s * st, 0f, s * st, s * ct)
        batch.lift = 0f

        batch.begin()
        when (state) {
            ST_MENU -> drawMenu()
            ST_PLAY -> { drawRing(); drawHud() }
            ST_ACT -> { drawRing(); drawHud(); drawActEnd() }
            else -> { drawRing(); drawOver() }
        }
        parts.draw(batch)
    }

    private fun step(dt: Float) {
        for (e in circus.update(dt)) when (e) {
            is Ev.Popped -> {
                val r = e.row.coerceIn(0, 2)
                // PITCHED PER BALLOON, so a streak does not sound like one
                // sample on repeat. Higher rows read as the smaller balloons and
                // a smaller balloon pops higher; the jitter keeps two pops in the
                // same row from landing identically.
                audio.sfx("pop", 0.94f + r * 0.07f +
                    (Random.nextFloat() - 0.5f) * 0.07f)
                parts.burst(fx(e.x), fy(e.y), 16, 0.06f, rowR[r], rowG[r], rowB[r], 0.6f)
                if (e.streak == 4 || e.streak == 8) {
                    quip = streakQuips[streakIdx++ % streakQuips.size]; quipT = 1.2f
                    audio.sfx("clap")
                }
            }
            is Ev.Bounced -> {
                // The boing is PITCHED BY THE LEVER. A catch on the tip is a
                // hard, high spring; a soft one near the pivot is a dull thud.
                // The player hears how good the catch was before they see how
                // high he goes.
                audio.sfx(if (e.hard) "boing" else "whee",
                    if (e.hard) (0.80f + e.power * 0.28f) else 1f)
                if (e.hard) {
                    val n = (6 + e.power * 12f).toInt()
                    parts.burst(fx(e.x), fy(0.05f), n, 0.04f + e.power * 0.035f,
                        0.6f, 1f, 0.9f, 0.35f + e.power * 0.2f)
                    // He only screams when the catch landed near the edge and
                    // he is actually going somewhere. The threshold sits above
                    // the power that first reaches the top row (about 1.13), so
                    // the scream means "this one is going all the way up" rather
                    // than firing on every decent catch and wearing out its
                    // welcome.
                    if (e.power > 1.25f) {
                        audio.sfx("yaao", 0.94f + (e.power - 1.25f) * 0.22f +
                            (Random.nextFloat() - 0.5f) * 0.06f)
                    }
                    if (e.power > 1.45f) { quip = "BIG ONE"; quipT = 0.9f }
                }
            }
            is Ev.Honk -> Unit
            is Ev.Splat -> {
                audio.sfx("splat"); shake = 1f
                quip = missQuips[missIdx++ % missQuips.size]; quipT = 2.0f
                parts.burst(fx(e.x), fy(0.02f), 30, 0.07f, 1f, 0.8f, 0.4f, 0.8f)
            }
            is Ev.RowCleared -> audio.sfx("clear")
            is Ev.ActDone -> { audio.sfx("clap"); state = ST_ACT; stateT = 0f }
            is Ev.Over -> { audio.sfx("hurt"); stopMusic(); state = ST_OVER; stateT = 0f }
        }
    }

    private fun fx(x: Float) = x * HALF_W + shakeU()
    private fun fy(y: Float) = BOT_V + y * (TOP_V - BOT_V) + shakeV()
    private fun shakeU() = if (shake <= 0f) 0f else sin(stateT * 55f) * 0.0020f * shake
    private fun shakeV() = if (shake <= 0f) 0f else cos(stateT * 39f) * 0.0020f * shake

    private fun drawRing() {
        // Big top: two poles and a swag of bunting. Cheap, and it says circus
        // before a single balloon is drawn.
        batch.line(-HALF_W, fy(0f), HALF_W, fy(0f), 0.0012f, 1f, 0.75f, 0.35f, 0.7f)
        for (s in intArrayOf(-1, 1)) {
            val u = s * HALF_W * 0.96f
            batch.line(u, fy(0f), u, fy(1.02f), 0.0007f, 1f, 0.6f, 0.3f, 0.35f)
        }
        var i = 0
        while (i <= 10) {
            val t0 = i / 10f
            val u0 = -HALF_W * 0.96f + t0 * (HALF_W * 1.92f)
            val sag = sin(t0 * 3.14159f) * 0.010f
            val v0 = fy(1.02f) - sag
            if (i < 10) {
                val t1 = (i + 1) / 10f
                val u1 = -HALF_W * 0.96f + t1 * (HALF_W * 1.92f)
                val v1 = fy(1.02f) - sin(t1 * 3.14159f) * 0.010f
                val k = i % 3
                batch.line(u0, v0, u1, v1, 0.0008f, rowR[k], rowG[k], rowB[k], 0.55f)
            }
            i++
        }

        for (b in circus.balloons) {
            if (!b.alive) continue
            val r = b.row.coerceIn(0, 2)
            val u = fx(circus.balloonX(b.col)); val v = fy(circus.balloonY(b.row))
            val bob = sin(stateT * 2.2f + b.col * 0.7f + b.row) * 0.0016f
            batch.fill(u, v + bob, 0.0075f, 0.0085f, 0f, rowR[r] * 0.45f, rowG[r] * 0.45f, rowB[r] * 0.45f, 0.75f)
            batch.circle(u, v + bob, 0.0092f, 0.0009f, rowR[r], rowG[r], rowB[r], 0.95f)
            batch.line(u, v + bob - 0.0090f, u, v + bob - 0.0135f, 0.0005f, 1f, 1f, 1f, 0.30f)
        }

        drawSeesaw()

        // TWO CLOWNS, ALWAYS. This was an if/else — while one was in the air
        // the other simply was not drawn, so the seesaw looked unattended and
        // the throw looked like the flying clown bouncing off an empty plank.
        // There have always been two of them; only one is ever airborne.
        val standU = fx(circus.seesawX + circus.loaded * END)
        val standV = fy(0.030f) - 0.0065f + 0.0080f
        drawClown(standU, standV, 0f, waiting = true)
        if (circus.airborne) drawClown(fx(circus.flyX), fy(circus.flyY), stateT * 7f)
    }

    private fun drawSeesaw() {
        val u = fx(circus.seesawX)
        val v = fy(0.030f)
        val w = END * HALF_W       // the plank IS the lever the rules measure
        val drop = 0.0065f

        // THE END WITH A CLOWN ON IT IS THE LOW ONE. His weight holds it down;
        // the empty end is raised, and that raised end is what the falling
        // clown has to hit. Drawing it the other way round read as a trampoline
        // instead of a lever.
        val loadedY = v - drop          // stander's end: down
        val raisedY = v + drop          // empty end: up, and the landing target
        val leftY = if (circus.loaded < 0) loadedY else raisedY
        val rightY = if (circus.loaded < 0) raisedY else loadedY
        batch.line(u - w, leftY, u + w, rightY, 0.0016f, 0.5f, 1f, 0.9f, 1f)

        batch.line(u, v - 0.001f, u - 0.007f, fy(0f), 0.0010f, 0.5f, 1f, 0.9f, 0.8f)
        batch.line(u, v - 0.001f, u + 0.007f, fy(0f), 0.0010f, 0.5f, 1f, 0.9f, 0.8f)

        // Mark the RAISED end, because that is where he has to land — the
        // player needs the target, not a reminder of where the other clown is
        // standing.
        val raised = -circus.loaded
        batch.circle(u + raised * w, raisedY, 0.0046f, 0.0009f,
            1f, 0.9f, 0.4f, 0.55f + 0.4f * sin(stateT * 6f))
    }

    /**
     * A clown, drawn as ridiculously as line art allows.
     *
     * Hair tufts, a ruffle collar, a cone hat, an enormous grin and boots two
     * sizes too big. He pinwheels his arms while airborne — a spinning clown is
     * funnier than a flying one, and the spin also tells you at a glance which
     * of the two is in the air.
     *
     * The waiting clown does not spin. He bobs, hopefully.
     */
    private fun drawClown(u: Float, v: Float, spin: Float, waiting: Boolean = false) {
        val bob = if (waiting) sin(stateT * 4f) * 0.0012f else 0f
        val y = v + bob
        // Everything below is expressed as a multiple of r, so this one number
        // resizes the whole clown and his proportions stay put.
        val r = 0.0052f

        // Boots. Comically wide, and the first thing you notice.
        val bootY = y - r - r * 0.47f
        batch.line(u - r * 1.46f, bootY, u - r * 0.42f, bootY, 0.0014f, 1f, 0.85f, 0.25f, 1f)
        batch.line(u + r * 0.42f, bootY, u + r * 1.46f, bootY, 0.0014f, 1f, 0.85f, 0.25f, 1f)
        batch.line(u - r * 0.55f, y - r, u - r * 1.04f, bootY, 0.0010f, 0.5f, 1f, 0.9f, 0.9f)
        batch.line(u + r * 0.55f, y - r, u + r * 1.04f, bootY, 0.0010f, 0.5f, 1f, 0.9f, 0.9f)

        // Ruffle collar: three scallops, which is all it takes to read as one.
        for (k in -1..1) {
            batch.circle(u + k * r * 0.58f, y - r * 0.72f, r * 0.36f, 0.0009f,
                1f, 0.35f, 0.65f, 0.95f)
        }

        // Head.
        batch.fill(u, y, r * 0.82f, r * 0.86f, 0f, 1f, 0.75f, 0.55f, 0.38f)
        batch.circle(u, y, r, 0.0011f, 1f, 0.85f, 0.6f, 1f)

        // Hair: a tuft either side, because bald plus hat is a magician.
        for (sgn in intArrayOf(-1, 1)) {
            val hx = u + sgn * r * 0.95f
            batch.line(hx, y + r * 0.17f, hx + sgn * r * 0.58f, y + r * 0.47f, 0.0010f, 1f, 0.35f, 0.25f, 1f)
            batch.line(hx, y - r * 0.11f, hx + sgn * r * 0.66f, y - r * 0.06f, 0.0010f, 1f, 0.35f, 0.25f, 1f)
            batch.line(hx, y - r * 0.36f, hx + sgn * r * 0.55f, y - r * 0.58f, 0.0010f, 1f, 0.35f, 0.25f, 1f)
        }

        // Cone hat with a pompom.
        batch.line(u - r * 0.80f, y + r * 0.80f, u + r * 0.80f, y + r * 0.80f, 0.0011f, 0.35f, 0.85f, 1f, 1f)
        batch.line(u - r * 0.61f, y + r * 0.80f, u, y + r * 1.94f, 0.0011f, 0.35f, 0.85f, 1f, 1f)
        batch.line(u + r * 0.61f, y + r * 0.80f, u, y + r * 1.94f, 0.0011f, 0.35f, 0.85f, 1f, 1f)
        batch.circle(u, y + r * 2.08f, r * 0.25f, 0.0009f, 1f, 0.9f, 0.35f, 1f)

        // Face: two dot eyes, a red nose, and a grin far too wide for the head.
        batch.circle(u - r * 0.36f, y + r * 0.25f, r * 0.13f, 0.0008f, 0.1f, 0.1f, 0.1f, 0.9f)
        batch.circle(u + r * 0.36f, y + r * 0.25f, r * 0.13f, 0.0008f, 0.1f, 0.1f, 0.1f, 0.9f)
        batch.circle(u, y - r * 0.06f, r * 0.30f, 0.0011f, 1f, 0.2f, 0.2f, 1f)
        batch.line(u - r * 0.58f, y - r * 0.36f, u - r * 0.25f, y - r * 0.64f, 0.0010f, 1f, 0.3f, 0.3f, 1f)
        batch.line(u - r * 0.25f, y - r * 0.64f, u + r * 0.25f, y - r * 0.64f, 0.0010f, 1f, 0.3f, 0.3f, 1f)
        batch.line(u + r * 0.25f, y - r * 0.64f, u + r * 0.58f, y - r * 0.36f, 0.0010f, 1f, 0.3f, 0.3f, 1f)

        // Arms. The airborne one windmills; the waiting one holds them up in
        // hope, which is somehow worse.
        if (waiting) {
            batch.line(u - r * 0.9f, y - 0.0010f, u - r * 1.75f, y + r * 0.58f, 0.0011f, 0.5f, 1f, 0.9f, 0.95f)
            batch.line(u + r * 0.9f, y - 0.0010f, u + r * 1.75f, y + r * 0.58f, 0.0011f, 0.5f, 1f, 0.9f, 0.95f)
        } else {
            for (k in 0..1) {
                val a = spin + k * 3.14159f
                batch.line(u + cos(a) * r * 0.95f, y + sin(a) * r * 0.95f,
                    u + cos(a) * r * 1.75f, y + sin(a) * r * 1.75f, 0.0011f, 0.5f, 1f, 0.9f, 0.95f)
            }
        }
    }

    private fun drawHud() {
        drawFit("${circus.score}", -0.132f, 0.104f, 0.0024f, 1f, 0.9f, 0.5f, 0.9f)
        drawFit("ACT $actNo", 0.078f, 0.104f, 0.0022f, 1f, 0.6f, 0.9f, 0.8f)
        var i = 0
        while (i < circus.lives) {
            batch.circle(-0.132f + i * 0.009f, 0.092f, 0.0024f, 0.0007f, 1f, 0.5f, 0.35f, 0.9f); i++
        }
        drawFit("${circus.aliveBalloons()} LEFT", -0.130f, -0.108f, 0.0020f,
            0.9f, 0.8f, 0.5f, 0.6f)
        if (quipT > 0f) {
            val a = (quipT / 1.2f).coerceIn(0f, 1f)
            drawFit(quip, 0f, 0.030f, 0.0028f, 1f, 0.85f, 0.4f, a * 0.95f, true)
        }
    }

    private fun drawMenu() {
        drawFit("CIRCUS", 0f, 0.062f, 0.0066f, 1f, 0.55f, 0.35f, 1f, true)
        val sel0 = row == 0
        drawFit("GRAVITY", -0.112f, 0.014f, 0.0028f, 0.55f, 0.9f, 1f, if (sel0) 1f else 0.45f)
        drawFit(if (settings.relaxed) "FORGIVING" else "NORMAL", 0.010f, 0.014f, 0.0028f,
            1f, 0.85f, 0.35f, if (sel0) 1f else 0.45f)
        if (sel0) caret(-0.132f, 0.014f, 0.0028f)
        val sel1 = row == 1
        val pulse = if (sel1) 0.55f + 0.45f * sin(stateT * 3f) else 0.4f
        drawFit("SEND HIM UP", 0f, -0.022f, 0.0040f, 1f, 1f, 0.6f, pulse, true)
        if (sel1) caret(-0.116f, -0.022f, 0.0040f)
        drawFit("DRAG   SLIDE THE SEESAW", -0.132f, -0.060f, 0.0019f, 0.5f, 0.9f, 1f, 0.5f)
        drawFit("TAP    HONK - STEERS HIM", -0.132f, -0.078f, 0.0019f, 0.5f, 0.9f, 1f, 0.5f)
        drawFit("BACK   LEAVE THE BIG TOP", -0.132f, -0.096f, 0.0019f, 0.5f, 0.9f, 1f, 0.38f)
    }

    /**
     * Draws text, shrinking it if it would run off the edge.
     *
     * The font advances about 5.4x its size parameter per character and the
     * visible field is +-0.144, so a 26-character quip at size 0.0028 wants
     * 0.39 of a 0.288 screen. Every overflow so far has been someone (me)
     * writing a longer string than the size allowed for, which is a bug that
     * should not need a person to notice it.
     */
    private fun drawFit(
        text: String, u: Float, v: Float, size: Float,
        r: Float, g: Float, b: Float, a: Float, centered: Boolean = false
    ) {
        val adv = 5.4f * text.length
        if (adv <= 0f) return
        val room = if (centered) EDGE * 2f else (EDGE - u)
        val fitted = minOf(size, room / adv)
        VectorFont.draw(batch, text, u, v, fitted, r, g, b, a, centered)
    }

    private fun caret(u: Float, v: Float, size: Float) {
        val h = size * 1.3f; val cy = v + size * 1.4f
        batch.line(u, cy + h, u + h * 1.2f, cy, 0.0010f, 1f, 1f, 0.6f, 0.9f)
        batch.line(u, cy - h, u + h * 1.2f, cy, 0.0010f, 1f, 1f, 0.6f, 0.9f)
    }

    private fun drawActEnd() {
        drawFit("ACT $actNo COMPLETE", 0f, 0.030f, 0.0036f, 1f, 0.85f, 0.4f, 1f, true)
        drawFit("${circus.score}", 0f, 0.004f, 0.0030f, 1f, 1f, 1f, 0.9f, true)
        val p = 0.5f + 0.5f * sin(stateT * 3f)
        drawFit("TAP FOR THE NEXT ACT", 0f, -0.026f, 0.0026f, 1f, 1f, 0.6f, p, true)
        if (stateT < 1.0f && parts.live < 240) parts.burst(0f, 0.030f, 6, 0.07f, 1f, 0.8f, 0.4f, 1.1f)
    }

    private fun drawOver() {
        drawFit("THAT IS THE SHOW", 0f, 0.036f, 0.0036f, 1f, 0.45f, 0.4f, 1f, true)
        drawFit("SCORE ${circus.score}", 0f, 0.008f, 0.0030f, 1f, 1f, 1f, 0.9f, true)
        drawFit("ACT $actNo", 0f, -0.014f, 0.0024f, 0.8f, 0.9f, 1f, 0.8f, true)
        val p = 0.5f + 0.5f * sin(stateT * 3f)
        drawFit("TAP TO TRY AGAIN", 0f, -0.044f, 0.0028f, 1f, 1f, 0.6f, p, true)
    }
}
