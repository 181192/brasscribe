package no.kalli.scribe.play.screen

import androidx.test.core.app.ApplicationProvider
import no.kalli.scribe.play.PlayApplication
import no.kalli.scribe.play.Product

/** The app these shared tests run in: each product module runs them under its own. */
val testedProduct: Product get() = ApplicationProvider.getApplicationContext<PlayApplication>().product
