package no.kalli.fretscribe

import no.kalli.scribe.tab.*

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import no.kalli.scribe.play.PlayApplication
import no.kalli.scribe.play.Product

/** The Fretscribe app. */
class FretscribeApplication : PlayApplication() {
    override val product: Product get() = Fretscribe
}
