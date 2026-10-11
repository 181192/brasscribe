package no.brasscribe.play.fret

import no.fretscribe.design.FretscribeColors
import no.fretscribe.design.FretscribeDarkColors
import no.fretscribe.design.FretscribeHighContrastColors
import no.fretscribe.design.FretscribeLightColors
import no.scribe.design.ScribeColors
import no.scribe.design.ScribeDarkColors
import no.scribe.design.ScribeHighContrastColors

/** Fretscribe's own colours that go with a palette of the roles every product has: the same mode's. */
internal fun own(colours: ScribeColors): FretscribeColors = when (colours) {
    ScribeHighContrastColors -> FretscribeHighContrastColors
    ScribeDarkColors -> FretscribeDarkColors
    else -> FretscribeLightColors
}
