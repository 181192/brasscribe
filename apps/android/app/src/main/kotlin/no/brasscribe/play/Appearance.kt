package no.brasscribe.play

import no.brasscribe.play.connection.KeyValueStore

/**
 * Settings › Display › Appearance (design/system.md §10): follow the phone, or force light or dark.
 * [PINK] is the hidden palette, listed only once it is unlocked from About; it follows the phone's
 * light or dark. It is kept on this phone only (excluded from backup and device transfer).
 */
enum class Appearance(val key: String) {
    SYSTEM("system"),
    LIGHT("light"),
    DARK("dark"),
    PINK("pink");

    /** Whether the app draws dark, given whether the phone is in dark theme. */
    fun isDark(systemDark: Boolean): Boolean = when (this) {
        SYSTEM, PINK -> systemDark
        LIGHT -> false
        DARK -> true
    }

    val isPink: Boolean get() = this == PINK

    companion object {
        /** An unknown or missing value is "Match system", the default. */
        fun fromKey(key: String?): Appearance = entries.firstOrNull { it.key == key } ?: SYSTEM
    }
}

/** Reads and writes the choice; the default is not written, so a phone that never chose has no entry. */
class AppearanceStore(private val store: KeyValueStore) {
    fun load(): Appearance = Appearance.fromKey(store.get(KEY))

    fun save(value: Appearance) {
        if (value == Appearance.SYSTEM) store.remove(KEY) else store.put(KEY, value.key)
    }

    /** Whether Pink has been unlocked on this phone. A stored Pink choice counts as unlocked. */
    fun pinkUnlocked(): Boolean = store.get(PINK_KEY) == "true" || load() == Appearance.PINK

    fun unlockPink() = store.put(PINK_KEY, "true")

    fun forgetPink() = store.remove(PINK_KEY)

    companion object {
        const val KEY = "appearance"
        const val PINK_KEY = "pinkUnlocked"
        /** Its own preferences file, so the backup rules can leave it out. */
        const val PREFS = "device"

        /** The choices the Appearance dialog lists: Pink only once it is unlocked. */
        fun choices(pinkUnlocked: Boolean): List<Appearance> =
            Appearance.entries.filter { it != Appearance.PINK || pinkUnlocked }
    }
}

/**
 * The easter egg on About: activating the version [TAPS] times, each within [WINDOW_MS] of the one
 * before, unlocks Pink. A longer pause starts the count again. [tap] is true exactly once, on the
 * activation that unlocks; after that it stays false, so the confirmation is said only once.
 */
class PinkUnlock(unlocked: Boolean, private val now: () -> Long = System::currentTimeMillis) {
    var unlocked = unlocked
        private set
    private var count = 0
    private var last = 0L

    fun tap(): Boolean {
        if (unlocked) return false
        val t = now()
        count = if (count > 0 && t - last <= WINDOW_MS) count + 1 else 1
        last = t
        if (count < TAPS) return false
        unlocked = true
        return true
    }

    companion object {
        const val TAPS = 5
        const val WINDOW_MS = 1_500L
    }
}
