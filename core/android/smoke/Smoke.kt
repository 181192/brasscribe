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
    check(humanizeUniform("") == 0.7636945250957473) { "humanize PRNG" }
    val h = humanizePart(listOf(ScoreNote(0, 24, 0.0, 0.5, 72, 80)), "Solo Cornet", 0, "brasscribe",
        Performance(composition), false)
    check(h.stats.voice == "melody") { "voice ${h.stats.voice}" }
    // talking-score-vectors.json: b-natural-norwegian-h
    val request = """
        {"part": {"name": "Solo Cornet", "transpose": {"chromatic": -2, "diatonic": -1}},
         "bar": {"number": 12, "key_fifths": 2},
         "event": {"kind": "note", "pos": {"beat": 4, "num": 3, "den": 4}, "type": "16th", "dots": 0,
                   "written": {"step": "B", "alter": 0, "octave": 4}, "concert": {"step": "A", "alter": 0, "octave": 4},
                   "confidence": 0.9, "sources": ["swiftf0", "muscriptor"]},
         "context": {"part": "Solo Cornet", "bar": 12}, "settings": {"lang": "nb"}}
    """.trimIndent()
    check(talkingAnnounceJson(request) == "slag 4, 4. av 4: H 4, sekstendedelsnote") { talkingAnnounceJson(request) }
    val ts = TalkingScore(xml, composition)
    val solo = ts.partNames().indexOf("Solo Cornet").toUInt()
    val line = ts.announce(TalkingCursor(solo, 0u, 0u), TalkingContext(), talkingSettingsDefault(), false)
    check(line.startsWith("bar 1, ")) { line }
    println("talking score: $line")
    println("instruments: ${instruments().size}; musicxml ${xml.length} chars; OK")
}
