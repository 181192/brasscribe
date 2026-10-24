package no.kalli.brasscribe

import no.kalli.scribe.play.*
import no.kalli.scribe.play.ui.*

import no.kalli.scribe.play.PlayApplication
import no.kalli.scribe.play.Product

/** The Brasscribe app. */
class BrasscribeApplication : PlayApplication() {
    override val product: Product get() = Brasscribe
}
