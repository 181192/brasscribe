package no.brasscribe.play.test

/**
 * An instrumented test that only a device can run: the real sound out (Oboe, sfizz, Media3 as it plays
 * by the clock), capture (the microphone, MediaProjection), the phone's own decoding of a recording,
 * memory, the frames the system counts, a foreground service, and alphaTab's page on a turned phone.
 * apps/android/scripts/device-tests.sh device-only runs these (and nothing else).
 */
@Retention(AnnotationRetention.RUNTIME)
@Target(AnnotationTarget.CLASS, AnnotationTarget.FUNCTION)
annotation class DeviceOnly

/** The short check that the app runs on a device at all: apps/android/scripts/device-tests.sh smoke. */
@Retention(AnnotationRetention.RUNTIME)
@Target(AnnotationTarget.CLASS, AnnotationTarget.FUNCTION)
annotation class Smoke
