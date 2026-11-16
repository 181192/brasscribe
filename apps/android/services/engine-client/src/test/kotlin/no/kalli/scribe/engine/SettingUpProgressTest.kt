package no.kalli.scribe.engine

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SettingUpProgressTest {
    private fun stage(id: Int, status: String, settingUp: String? = null, fraction: Double? = null) =
        JobEvent(id, "stage", stage = "stems", kind = "stems", status = status, settingUp = settingUp, fraction = fraction, time = 100.0 + id)

    @Test
    fun aStartedStageSettingUpShowsUntilTheStageHasItsModel() {
        val t = ProgressTracker(stagesTotal = 2)
        assertFalse(t.onEvent(JobEvent(0, "job", status = "running", time = 100.0)).settingUp)
        assertTrue(t.onEvent(stage(1, "started", settingUp = "separator")).settingUp)
        assertFalse(t.onEvent(stage(2, "started")).settingUp)
        assertFalse(t.onEvent(stage(3, "ran", fraction = 0.5)).settingUp)
    }

    @Test
    fun aJobThatEndsWhileSettingUpClearsIt() {
        val t = ProgressTracker(stagesTotal = 2)
        assertTrue(t.onEvent(stage(1, "started", settingUp = "beat-this")).settingUp)
        assertFalse(t.onEvent(JobEvent(2, "job", status = "cancelled", time = 110.0)).settingUp)
    }

    @Test
    fun theFixtureComputerPlaysTheSetUp() = runTest {
        var setting: String? = "separator"
        val api = FixtureEngineApi({ null }, stageSeconds = 0.0, settingUp = { setting.also { setting = null } })
        val job = api.createJobFromUpload("a.wav", ByteArray(8), Profile.ORCHESTRA_WITH_SOLOIST, "A")
        val t = ProgressTracker(job.stages.size)
        val ps = api.events(job.id).toList().map { t.onEvent(it).settingUp }
        assertEquals(1, ps.count { it })
        assertFalse(ps.last())
    }
}
