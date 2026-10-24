package no.kalli.scribe.test

/**
 * JUnit category of tests that take seconds. `./gradlew testDebugUnitTest -Pscribe.fast` leaves them out
 * (docs/dev/verify.md); every other run includes them. Each module with slow tests has its own copy:
 * categories match by name.
 */
interface Slow
