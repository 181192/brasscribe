package no.brasscribe.play.fret

import no.kalli.fretscribe.design.FretscribeColors
import no.kalli.fretscribe.design.FretscribeDarkColors
import no.kalli.fretscribe.design.FretscribeHighContrastColors
import no.kalli.fretscribe.design.FretscribeHighContrastLightColors
import no.kalli.fretscribe.design.FretscribeLightColors
import no.kalli.scribe.design.ScribeColors
import no.kalli.scribe.design.ScribeDarkColors
import no.kalli.scribe.design.ScribeHighContrastColors
import no.kalli.scribe.design.ScribeHighContrastLightColors

/** Fretscribe's own colours that go with a palette of the roles every product has: the same mode's. */
internal fun own(colours: ScribeColors): FretscribeColors = when (colours) {
    ScribeHighContrastColors -> FretscribeHighContrastColors
    ScribeHighContrastLightColors -> FretscribeHighContrastLightColors
    ScribeDarkColors -> FretscribeDarkColors
    else -> FretscribeLightColors
}
