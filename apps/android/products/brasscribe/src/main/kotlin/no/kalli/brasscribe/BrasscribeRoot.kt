package no.kalli.brasscribe

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import no.kalli.brasscribe.ui.BrasscribeSettingsScreen
import no.kalli.brasscribe.ui.OutputScreen
import no.kalli.brasscribe.ui.ProfileScreen
import no.kalli.brasscribe.ui.ReviewScreen
import no.kalli.brasscribe.ui.ScoreScreen
import no.kalli.brasscribe.ui.WhatDoYouPlayScreen
import no.kalli.scribe.play.PlayViewModel
import no.kalli.scribe.play.Screen
import no.kalli.scribe.play.ui.AboutScreen
import no.kalli.scribe.play.ui.CompanionScreen
import no.kalli.scribe.play.ui.ExportScreen
import no.kalli.scribe.play.ui.FirstRunScreen
import no.kalli.scribe.play.ui.HelpScreen
import no.kalli.scribe.play.ui.HomeScreen
import no.kalli.scribe.play.ui.ProblemScreen
import no.kalli.scribe.play.ui.RecordScreen
import no.kalli.scribe.play.ui.TranscribeScreen

/** Brasscribe's navigation: a screen for each place on the stack. */
@Composable
fun BrasscribeRoot(vm: PlayViewModel) {
    val stack by vm.screen.collectAsState()
    BackHandler(enabled = stack.size > 1) { vm.back() }
    when (stack.last()) {
        Screen.FIRST_RUN -> FirstRunScreen(vm)
        Screen.WHAT_DO_YOU_PLAY -> WhatDoYouPlayScreen(vm)
        Screen.HOME -> HomeScreen(vm)
        Screen.RECORD -> RecordScreen(vm)
        Screen.PROFILE -> ProfileScreen(vm)
        Screen.TRANSCRIBE -> TranscribeScreen(vm)
        Screen.REVIEW -> ReviewScreen(vm)
        Screen.OUTPUT -> OutputScreen(vm)
        Screen.SCORE -> ScoreScreen(vm)
        Screen.EXPORT -> ExportScreen(vm)
        Screen.COMPANION -> CompanionScreen(vm)
        Screen.ABOUT -> AboutScreen(vm)
        Screen.SETTINGS -> BrasscribeSettingsScreen(vm)
        Screen.HELP -> HelpScreen(vm)
        Screen.PROBLEM -> ProblemScreen(vm)
    }
}
