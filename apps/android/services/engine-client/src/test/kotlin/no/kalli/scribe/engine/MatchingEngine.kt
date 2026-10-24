package no.kalli.scribe.engine

import io.ktor.client.engine.HttpClientEngine

/**
 * A client of an engine already known to speak this app's interface version, for the tests of what comes after
 * that: their engines answer the one request the test is about, and no health. (InterfaceMatchTest tests the gate.)
 */
internal fun matchingEngine(baseUrl: String, engine: HttpClientEngine, token: String? = null): KtorEngineApi =
    KtorEngineApi(baseUrl, engine, token).also { it.interfaceMatch = InterfaceMatch.MATCH }
