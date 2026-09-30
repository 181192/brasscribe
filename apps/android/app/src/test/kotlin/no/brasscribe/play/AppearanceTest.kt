package no.brasscribe.play

import no.brasscribe.play.connection.CredentialStoreTest.MemoryStore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AppearanceTest {
    @Test fun matchSystemFollowsThePhone() {
        assertTrue(Appearance.SYSTEM.isDark(systemDark = true))
        assertFalse(Appearance.SYSTEM.isDark(systemDark = false))
    }

    @Test fun lightAndDarkIgnoreThePhone() {
        for (system in listOf(true, false)) {
            assertFalse(Appearance.LIGHT.isDark(system))
            assertTrue(Appearance.DARK.isDark(system))
        }
    }

    @Test fun missingOrUnknownValueIsMatchSystem() {
        assertEquals(Appearance.SYSTEM, Appearance.fromKey(null))
        assertEquals(Appearance.SYSTEM, Appearance.fromKey("sepia"))
        assertEquals(Appearance.DARK, Appearance.fromKey("dark"))
    }

    @Test fun storeRoundTripsAndDropsTheDefault() {
        val mem = MemoryStore()
        val store = AppearanceStore(mem)
        assertEquals(Appearance.SYSTEM, store.load())
        store.save(Appearance.DARK)
        assertEquals("dark", mem.map[AppearanceStore.KEY])
        assertEquals(Appearance.DARK, AppearanceStore(mem).load())
        store.save(Appearance.LIGHT)
        assertEquals(Appearance.LIGHT, store.load())
        store.save(Appearance.SYSTEM)
        assertNull(mem.map[AppearanceStore.KEY])
        assertEquals(Appearance.SYSTEM, store.load())
    }

    @Test fun pinkLightAndPinkDarkIgnoreThePhone() {
        for (system in listOf(true, false)) {
            assertFalse(Appearance.PINK_LIGHT.isDark(system))
            assertTrue(Appearance.PINK_DARK.isDark(system))
        }
        assertEquals(Appearance.PINK_LIGHT, Appearance.fromKey("pink-light"))
        assertEquals(Appearance.PINK_DARK, Appearance.fromKey("pink-dark"))
        assertTrue(Appearance.PINK_LIGHT.isPink)
        assertTrue(Appearance.PINK_DARK.isPink)
        assertFalse(Appearance.DARK.isPink)
    }

    @Test fun pinkIsHiddenUntilUnlockedAndTheUnlockIsKept() {
        val mem = MemoryStore()
        val store = AppearanceStore(mem)
        assertFalse(store.pinkUnlocked())
        assertEquals(listOf(Appearance.SYSTEM, Appearance.LIGHT, Appearance.DARK), AppearanceStore.choices(store.pinkUnlocked()))
        store.unlockPink()
        assertEquals("true", mem.map[AppearanceStore.PINK_KEY])
        assertTrue(AppearanceStore(mem).pinkUnlocked())
        // After Match system, Light and Dark.
        assertEquals(
            listOf(Appearance.SYSTEM, Appearance.LIGHT, Appearance.DARK, Appearance.PINK_LIGHT, Appearance.PINK_DARK),
            AppearanceStore.choices(true),
        )
        // Switching it off is choosing another option; Pink stays listed.
        store.save(Appearance.PINK_DARK)
        assertEquals("pink-dark", mem.map[AppearanceStore.KEY])
        assertEquals(Appearance.PINK_DARK, AppearanceStore(mem).load())
        store.save(Appearance.LIGHT)
        assertTrue(store.pinkUnlocked())
    }

    @Test fun storedPinkCountsAsUnlocked() {
        for (key in listOf("pink-light", "pink-dark", "pink")) {
            assertTrue(AppearanceStore(MemoryStore(linkedMapOf(AppearanceStore.KEY to key))).pinkUnlocked())
        }
    }

    @Test fun theOldPinkBecomesPinkLightOrDarkByThePhone() {
        for ((systemDark, expected) in listOf(true to Appearance.PINK_DARK, false to Appearance.PINK_LIGHT, null to Appearance.PINK_LIGHT)) {
            val mem = MemoryStore(linkedMapOf(AppearanceStore.KEY to "pink"))
            val store = AppearanceStore(mem)
            store.migrate(systemDark)
            assertEquals(expected, store.load())
            assertEquals(expected.key, mem.map[AppearanceStore.KEY])
            // Written down, so an earlier version still lists Pink after reading the new value as Match system.
            assertEquals("true", mem.map[AppearanceStore.PINK_KEY])
        }
    }

    @Test fun migrationLeavesEveryOtherChoiceAlone() {
        for (key in listOf(null, "system", "light", "dark", "pink-light", "pink-dark", "sepia")) {
            val mem = MemoryStore(if (key == null) linkedMapOf() else linkedMapOf(AppearanceStore.KEY to key))
            AppearanceStore(mem).migrate(systemDark = true)
            assertEquals(key, mem.map[AppearanceStore.KEY])
            assertNull(mem.map[AppearanceStore.PINK_KEY])
        }
    }

    @Test fun fiveQuickTapsUnlockOnce() {
        var t = 0L
        val u = PinkUnlock(unlocked = false) { t }
        repeat(4) { assertFalse(u.tap()); t += 1_000 }
        assertTrue(u.tap())
        assertTrue(u.unlocked)
        // No second confirmation.
        repeat(6) { assertFalse(u.tap()) }
    }

    @Test fun aLongPauseStartsTheCountAgain() {
        var t = 0L
        val u = PinkUnlock(unlocked = false) { t }
        repeat(4) { assertFalse(u.tap()); t += 100 }
        t += PinkUnlock.WINDOW_MS + 1
        repeat(4) { assertFalse(u.tap()); t += PinkUnlock.WINDOW_MS }
        assertTrue(u.tap())
    }

    @Test fun alreadyUnlockedNeverConfirmsAgain() {
        val u = PinkUnlock(unlocked = true) { 0L }
        repeat(10) { assertFalse(u.tap()) }
    }
}
