// JVM smoke test of the Kotlin bindings against the host library:
//   core/android/smoke/run.sh
import uniffi.brasscribe_ffi.*

fun main() {
    val composition = """
        {"title": "Test", "voices": [
          {"id": "melody", "role": "melody", "notes": [
            {"pitch": 72, "start": 0, "dur": 24}, {"pitch": 74, "start": 24, "dur": 24}]},
          {"id": "bass", "role": "bass", "notes": [{"pitch": 48, "start": 0, "dur": 48}]}],
         "meters": [{"tick": 0, "beats": 4}], "keys": [{"tick": 0, "fifths": 0}]}
    """.trimIndent()
    println("core ${coreVersion()}")
    val xml = arrangeMusicxml(composition, "auto")
    check(xml.contains("<part-name>Solo Cornet</part-name>")) { "no Solo Cornet part" }
    check(xml.contains("<step>D</step>")) { "cornet not transposed" }
    val spelled = spellPitches(listOf(0.0, 1.0, 2.0), listOf(66, 69, 74))
    check(spelled.map { it.step } == listOf("F", "A", "D")) { "spelling $spelled" }
    try {
        normalizeComposition("{")
        error("invalid JSON accepted")
    } catch (e: CoreException.Invalid) {
        println("invalid input rejected: ${e.message}")
    }
    println("instruments: ${instruments().size}; musicxml ${xml.length} chars; OK")
}
