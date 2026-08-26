package com.x3.circus.game

import kotlin.math.abs
import kotlin.math.sqrt
import kotlin.random.Random

/** Ring is normalised: x -1..1 across, y 0 at the seesaw and 1 at the top. */
const val ROWS = 3
const val PER_ROW = 10

/**
 * Distance from the fulcrum to either end, in field units.
 *
 * THE RENDERER AND THE RULES MUST AGREE ON THIS. They did not: the model put
 * the ends at 0.13 while the plank was drawn at 0.24 and the target marker at
 * 0.22, so the spot the player was aiming at was nowhere near the spot the
 * lever maths was measuring from. Both now read this.
 */
const val END = 0.22f

/** How far either side of an end still counts as a catch. Generous by design. */
const val CATCH = 0.16f

/**
 * Apex, in field units, as a function of lever power: APEX_BASE + APEX_GAIN*p.
 *
 * IT IS LINEAR IN POWER ON PURPOSE. Torque times distance is WORK, work is
 * energy, and energy is height - so mechanical advantage should buy apex
 * directly. Driving the launch VELOCITY with power instead made apex go as
 * power SQUARED, and the whole top of the range slammed into the tent roof.
 *
 * THE SLOPE IS SET BY WHERE THE TOP ROW IS, not by taste. Measured on device
 * with the previous 0.34 + 0.38p curve, a catch had to land past landOut +0.4
 * before it reached row 2 at all, and even then it apexed at 0.88 - exactly the
 * row's own height, grazing it with no margin. Landing near the edge is supposed
 * to be the payoff of the whole game, so the curve now pivots about the weak end
 * and lifts the strong end until:
 *
 *   power 0.70  well inboard      apex 0.58   row 0 only
 *   power 1.00  square on the end apex 0.75   row 1
 *   power 1.14  edging outboard   apex 0.83   ROW 2 - the upper balloons
 *   power 1.36  near the edge     apex 0.95   clears row 2 with room
 *   power 1.49+ on the tip        apex 1.02+  HITS THE BIG TOP and bounces
 *
 * The tent bonk at the very top is deliberate. The roof is drawn at 1.02 and the
 * visible field runs out around 1.06, so there is nowhere above it to go anyway;
 * making the biggest launches audibly and visibly hit the canvas turns the
 * ceiling from a silent clamp into the loudest possible "that was a big one".
 */
const val APEX_BASE = 0.19f
const val APEX_GAIN = 0.56f
const val BASE_LAUNCH = 1.34f

class Balloon(@JvmField var row: Int, @JvmField var col: Int, @JvmField var alive: Boolean = true)

sealed class Ev {
    class Popped(val x: Float, val y: Float, val row: Int, val points: Int, val streak: Int) : Ev()
    /** [power] is the lever ratio: 1 is a nominal throw, above 1 is a big one. */
    class Bounced(val x: Float, val hard: Boolean, val power: Float) : Ev()
    object Honk : Ev()
    class Splat(val x: Float) : Ev()
    object RowCleared : Ev()
    object ActDone : Ev()
    object Over : Ev()
}

/**
 * ============================================================================
 *  CIRCUS — the 1977 cabinet, with the difficulty taken out of it.
 * ============================================================================
 *
 * A clown falls. You slide a seesaw under him. He lands on one end, which flings
 * the OTHER clown up into the balloons. Miss, and he hits the sawdust.
 *
 * That is the whole 1977 game and it is a good one, but it is also brutal: the
 * original seesaw is small, the clown is fast, and a miss is instant. The brief
 * here was hilarious and not too difficult, so three things are different:
 *
 *  - The seesaw is WIDE and the catch window is generous.
 *  - A honk (tap) nudges the airborne clown sideways in mid-flight. It is the
 *    silliest possible steering mechanism and it turns a miss you can see
 *    coming into a miss you had a chance to fix.
 *  - Missing costs a life but the clown bounces back on with a rude noise
 *    rather than ending the act.
 *
 * No Android, no GL: rules only.
 */
class Circus(seed: Long = 0x43495243L) {

    private val rnd = Random(seed)

    @JvmField val balloons = ArrayList<Balloon>(ROWS * PER_ROW)

    var seesawX = 0f; private set
    /**
     * Which end a clown is STANDING on: -1 left, +1 right.
     *
     * That end is the LOW one — his weight holds it down — and the empty end is
     * therefore the raised one. The falling clown lands on the raised end, and
     * it is his arrival that drives it down and throws the stander off the
     * other side. Getting this backwards makes the whole prop read as a
     * trampoline rather than a lever.
     */
    var loaded = -1; private set

    var flyX = 0f; private set
    var flyY = 0f; private set
    private var vx = 0f
    private var vy = 0f
    var airborne = false; private set

    var score = 0; private set
    var lives = 3; private set
    var act = 1; private set
    var streak = 0; private set
    var over = false; private set
    var actDone = false; private set

    private var gravity = 1.05f
    private var launch = 1.34f
    private var honkPush = 0.55f
    private var respawn = 0f
    private val evs = ArrayList<Ev>(16)

    fun aliveBalloons() = balloons.count { it.alive }

    fun startAct(a: Act, fresh: Boolean) {
        if (fresh) { score = 0; lives = 3; over = false }
        act = a.n
        gravity = a.gravity
        launch = a.launch
        actDone = false
        streak = 0
        balloons.clear()
        for (r in 0 until ROWS) for (c in 0 until PER_ROW) balloons.add(Balloon(r, c))
        seesawX = 0f
        loaded = -1
        airborne = false
        respawn = 0.6f
    }

    fun moveTo(x: Float) { seesawX = x.coerceIn(-0.82f, 0.82f) }

    /** The honk. Comedy first, steering second — but it really does steer. */
    fun honk(): Boolean {
        evs.add(Ev.Honk)
        if (!airborne) return false
        // Nudge toward wherever the seesaw is, because that is what the player
        // is already pointing at. One control, two jobs.
        val dir = if (seesawX > flyX) 1f else -1f
        vx += dir * honkPush
        vx = vx.coerceIn(-0.85f, 0.85f)
        return true
    }

    fun update(dt: Float): List<Ev> {
        evs.clear()
        if (over || actDone) return evs
        val h = if (dt.isNaN()) 0f else dt.coerceIn(0f, 0.05f)

        if (!airborne) {
            respawn -= h
            if (respawn <= 0f) fling()
            return evs
        }

        vy -= gravity * h
        flyX += vx * h
        flyY += vy * h

        // WALLS AND CANVAS ARE ALL IN PLAY. With the throws now spread wide, a
        // clown who reaches the side has to come BACK — otherwise the flight
        // ends against the tent pole and he drops somewhere the seesaw cannot
        // reach. A lively bounce keeps him in the ring and gives the player a
        // second chance to slide under him.
        if (flyX < -0.94f) { flyX = -0.94f; vx = abs(vx) * 0.96f + 0.05f }
        if (flyX > 0.94f) { flyX = 0.94f; vx = -abs(vx) * 0.96f - 0.05f }
        // And off the top of the tent, which also stops a big throw vanishing
        // out of view for a second and a half.
        if (flyY > 1.02f && vy > 0f) { flyY = 1.02f; vy = -abs(vy) * 0.55f }

        popCheck()

        if (flyY <= 0.055f && vy < 0f) landing()
        return evs
    }

    /**
     * Opening throw of an act. The stander is on the low end, so he is the one
     * launched — from his own side.
     */
    private fun fling() {
        airborne = true
        flyX = seesawX + loaded * END
        flyY = 0.06f
        vy = apexVy(1.0f) * (0.98f + rnd.nextFloat() * 0.04f)
        vx = loaded * (0.18f + rnd.nextFloat() * 0.16f)
        evs.add(Ev.Bounced(flyX, false, 1f))
    }

    private fun popCheck() {
        for (b in balloons) {
            if (!b.alive) continue
            val bx = balloonX(b.col)
            val by = balloonY(b.row)
            if (abs(flyX - bx) > 0.070f || abs(flyY - by) > 0.055f) continue
            b.alive = false
            streak++
            // A streak inside one flight is where the score comes from, which
            // rewards a good launch rather than grinding.
            val pts = (10 + b.row * 10) * (1 + streak / 4)
            score += pts
            evs.add(Ev.Popped(bx, by, b.row, pts, streak))
            if (balloons.none { it.alive && it.row == b.row }) evs.add(Ev.RowCleared)
            if (balloons.none { it.alive }) { actDone = true; evs.add(Ev.ActDone) }
            return
        }
    }

    /**
     * The upward speed needed to reach the apex this lever power has earned,
     * from wherever he is standing right now. Solved from v = sqrt(2*g*h), so
     * a heavier act (higher gravity) shortens the HANG TIME rather than
     * flattening the arc — the balloon rows are at fixed heights and must stay
     * reachable however many laps deep the player is.
     */
    private fun apexVy(power: Float): Float {
        val target = (APEX_BASE + APEX_GAIN * power) * (launch / BASE_LAUNCH)
        return sqrt(2f * gravity * (target - flyY).coerceAtLeast(0.05f))
    }

    private fun landing() {
        // He must come down on the RAISED end — the empty one, opposite the
        // stander. GENEROUS ON PURPOSE: the 1977 seesaw is unforgiving and the
        // brief was not to be.
        val raised = -loaded
        val end = seesawX + raised * END
        if (abs(flyX - end) <= CATCH) {
            // He lands, that end goes down, and HE becomes the stander on it.
            // The clown who was standing on the low end is the one thrown — so
            // the flight restarts from the OPPOSITE side, not from where this
            // one landed. Continuing from the landing point was the bug: it
            // made one clown bounce like a ball instead of two clowns working a
            // lever.
            val thrownFrom = loaded

            // IT IS A LEVER, SO TORQUE IS FORCE TIMES DISTANCE FROM THE PIVOT.
            //
            // armIn is how far out along the plank he actually landed; armOut
            // is where the other clown is standing, which is fixed at the end.
            // The ratio between them is the mechanical advantage, and it is the
            // whole skill of the game: catch him on the very tip and the other
            // one is fired at the top row, catch him halfway in and he barely
            // clears the plank.
            //
            // This used to run BACKWARDS — vy carried a "- lever * 0.06" term,
            // so landing far out made the throw WEAKER. It felt wrong for a
            // reason: every seesaw anyone has ever used does the opposite.
            val armIn = abs(flyX - seesawX)
            val armOut = END
            val power = (armIn / armOut).coerceIn(0.70f, 1.75f)

            // How far OUTBOARD of the end he struck, normalised to the catch
            // window and signed so +1 is always "past the tip" whichever end
            // it was. MEASURE IT NOW: flyX is about to be moved to the launch
            // point, and reading it afterwards was the bug — (flyX - end) then
            // evaluates to a fixed 2*END, which saturates the ratio at ±1 every
            // single time and made this term a constant.
            val landOut = ((flyX - end) * raised / CATCH).coerceIn(-1f, 1f)

            loaded = raised
            flyX = seesawX + thrownFrom * END
            flyY = 0.06f
            // Vertical is what the lever buys. The floor of 0.70 is mercy: a
            // sloppy catch still gets him high enough to be caught again rather
            // than starting a spiral the player cannot escape.
            vy = apexVy(power) * (0.98f + rnd.nextFloat() * 0.04f)
            // Sideways comes from WHERE on the end he struck it — outboard of
            // centre throws outward, inboard throws back across the ring — plus
            // a little scatter so no two throws repeat.
            // Outboard catches throw him further across the ring, inboard
            // ones lob him closer to home.
            vx = thrownFrom * (0.16f + power * 0.10f + landOut * 0.13f) +
                 (rnd.nextFloat() - 0.5f) * 0.12f
            streak = 0
            evs.add(Ev.Bounced(flyX, true, power))
        } else {
            airborne = false
            streak = 0
            respawn = 1.0f
            lives--
            evs.add(Ev.Splat(flyX))
            if (lives <= 0) { over = true; evs.add(Ev.Over) }
        }
    }

    fun balloonX(col: Int) = -0.81f + col * 0.18f
    fun balloonY(row: Int) = 0.60f + row * 0.14f
}

class Act(
    @JvmField val n: Int, @JvmField val name: String,
    @JvmField val gravity: Float, @JvmField val launch: Float,
    @JvmField val music: Int, @JvmField val quip: String
)

/**
 * Four acts, cycling. The ramp is very gentle: gravity creeps up so flights get
 * shorter, and that is all. The brief said not too difficult and meant it.
 */
object Acts {
    val all = listOf(
        Act(1, "THE GRAND ENTRY", 1.00f, 1.34f, 0, "MIND THE CLOWN"),
        Act(2, "THE WOBBLE",      1.08f, 1.36f, 1, "HE IS DOING HIS BEST"),
        Act(3, "THE HIGH ONES",   1.16f, 1.40f, 1, "HONK TO STEER HIM"),
        Act(4, "THE BIG FINISH",  1.24f, 1.44f, 2, "NOBODY IS INSURED")
    )
    val count get() = all.size
    fun get(n: Int): Act {
        val i = n.coerceAtLeast(1)
        val lap = (i - 1) / count
        val b = all[(i - 1) % count]
        if (lap == 0) return b
        return Act(i, b.name, (b.gravity * (1f + 0.06f * lap)).coerceAtMost(1.7f),
            b.launch, b.music, b.quip)
    }
}
