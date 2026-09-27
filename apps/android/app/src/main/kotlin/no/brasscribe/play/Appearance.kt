package no.brasscribe.play

import no.brasscribe.play.connection.KeyValueStore

/**
 * Settings › Display › Appearance (design/system.md §10): follow the phone, or force light or dark.
 * It is kept on this phone only (excluded from backup and device transfer).
 */
enum class Appearance(val key: String) {
    SYSTEM("system"),
    LIGHT("light"),
    DARK("dark");

    /** Whether the app draws dark, given whether the phone is in dark theme. */
    fun isDark(systemDark: Boolean): Boolean = when (this) {
        SYSTEM -> systemDark
        LIGHT -> false
        DARK -> true
    }

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

    companion object {
        const val KEY = "appearance"
        /** Its own preferences file, so the backup rules can leave it out. */
        const val PREFS = "device"
    }
}
