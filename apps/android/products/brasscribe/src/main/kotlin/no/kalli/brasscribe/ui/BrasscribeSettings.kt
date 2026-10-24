package no.kalli.brasscribe.ui

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.stringResource
import no.kalli.brasscribe.R
import no.kalli.scribe.audio.RealisticSynth
import no.kalli.scribe.play.PlayViewModel
import no.kalli.scribe.play.ui.ChoiceCard
import no.kalli.scribe.play.ui.ChoiceGroup
import no.kalli.scribe.play.ui.RowDivider
import no.kalli.scribe.play.ui.RowGroup
import no.kalli.scribe.play.ui.SectionLabel
import no.kalli.scribe.play.ui.SettingsScreen
import no.kalli.scribe.play.ui.SwitchRow

/** Settings with Brasscribe's own sections: the band's sound, and the music stand (design/music-stand.md section 9). */
@Composable
fun BrasscribeSettingsScreen(vm: PlayViewModel) = SettingsScreen(vm, beforeDisplay = { SoundSettings(vm) }, afterDisplay = { StandSettings(vm) })

/** The band's instruments: the standard sound or the realistic one. */
@Composable
private fun SoundSettings(vm: PlayViewModel) {
    var realistic by rememberSaveable { mutableStateOf(vm.container.realisticByDefault) }
    SectionLabel(stringResource(R.string.sound))
    ChoiceGroup(2) {
        ChoiceCard(stringResource(R.string.sound_baseline), stringResource(R.string.settings_sound_standard), !realistic, true, 0) {
            realistic = false; vm.container.realisticByDefault = false
        }
        ChoiceCard(stringResource(R.string.sound_realistic), stringResource(R.string.settings_sound_realistic), realistic,
            RealisticSynth.available, 1) { realistic = true; vm.container.realisticByDefault = true }
    }
}

/** The music stand: whether it follows the playing, and whether its controls stay shown. */
@Composable
private fun StandSettings(vm: PlayViewModel) {
    SectionLabel(stringResource(R.string.stand_enter))
    RowGroup {
        var follow by rememberSaveable { mutableStateOf(vm.container.standFollow) }
        var keep by rememberSaveable { mutableStateOf(vm.container.standKeepControls) }
        SwitchRow(stringResource(R.string.settings_stand_follow), null, follow, "setting-stand-follow") { follow = it; vm.container.standFollow = it }
        RowDivider()
        SwitchRow(stringResource(R.string.settings_stand_controls), null, keep, "setting-stand-controls") { keep = it; vm.container.standKeepControls = it }
    }
}
