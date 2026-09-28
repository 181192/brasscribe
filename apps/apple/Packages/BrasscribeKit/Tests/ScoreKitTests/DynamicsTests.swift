import Foundation
import Testing
@testable import ScoreKit

/// sounds/playback-levels.json "dynamics": the velocity rules every Play app shares.
func sharedDynamics() -> [String: Any]? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        let f = dir.appending(path: "sounds/playback-levels.json")
        if let d = try? Data(contentsOf: f), let doc = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
            return doc["dynamics"] as? [String: Any]
        }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

/// One 4/4 part (divisions 1) from measure bodies; `note` writes a quarter note.
private func part(_ measures: [String], percussion: Bool = false) throws -> Score {
    let body = measures.enumerated().map { i, m in
        let attrs = i > 0 ? "" : """
        <attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>\(percussion ? "percussion" : "G")</sign></clef></attributes>
        """
        return "<measure number=\"\(i + 1)\">\(attrs)\(m)</measure>"
    }.joined()
    let xml = """
    <?xml version="1.0"?><score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Cornet</part-name></score-part></part-list>
    <part id="P1">\(body)</part></score-partwise>
    """
    return try MusicXMLParser.parse(Data(xml.utf8))
}

private func note(_ step: String = "C", _ notations: String = "") -> String {
    "<note><pitch><step>\(step)</step><octave>5</octave></pitch><duration>1</duration><type>quarter</type>\(notations)</note>"
}
private func dyn(_ d: String) -> String { "<direction><direction-type><dynamics><\(d)/></dynamics></direction-type></direction>" }
private func wedge(_ t: String) -> String { "<direction><direction-type><wedge type=\"\(t)\"/></direction-type></direction>" }
private func velocities(_ s: Score) -> [Int] { s.parts[0].playbackNotes.map(\.velocity) }

@Test(.enabled(if: sharedDynamics() != nil)) func velocityTableMatchesPlaybackLevels() throws {
    let d = try #require(sharedDynamics())
    #expect(d["default"] as? String == Dynamics.defaultMark)
    #expect(d["step"] as? Int == Dynamics.step)
    #expect(d["velocity"] as? [String: Int] == Dynamics.velocity)
    #expect(d["accent_steps"] as? [String: Int] == Dynamics.accentSteps)
    // alphaTab MidiUtils: 15 + 16 per step from ppp to fff
    for (i, m) in ["ppp", "pp", "p", "mp", "mf", "f", "ff", "fff"].enumerated() { #expect(Dynamics.velocity(mark: m) == 15 + 16 * i) }
}

/// A part starts at f; each mark holds until the next, including the forced ones, as alphaTab plays them.
@Test func marksHoldInDocumentOrder() throws {
    let s = try part([
        note() + dyn("pp") + note() + dyn("p") + note() + dyn("mf") + note(),
        dyn("ff") + note() + dyn("sfz") + note() + note() + dyn("mp") + note(),
    ])
    #expect(velocities(s) == [95, 31, 47, 79, 111, 111, 111, 63])
    #expect(s.parts[0].dynamics[960] == "pp")
    #expect(s.parts[0].notes.map(\.dynamic) == ["f", "pp", "p", "mf", "ff", "sfz", "sfz", "mp"])
    // <sound dynamics> alone changes nothing
    let quiet = try part(["<direction><direction-type><words>x</words></direction-type><sound dynamics=\"40\"/></direction>" + note()])
    #expect(velocities(quiet) == [95])
}

/// A mark in a note's notations applies from that note on; so does the next part's own default.
@Test func noteDynamicsAndAccents() throws {
    let accent = "<notations><articulations><accent/></articulations></notations>"
    let marcato = "<notations><articulations><strong-accent/></articulations></notations>"
    let s = try part([
        dyn("mf") + note() + note("D", accent) + note("E", marcato) + note("F", "<notations><articulations><tenuto/></articulations></notations>"),
        dyn("fff") + note("C", marcato) + note("C", "<notations><dynamics><p/></dynamics></notations>") + note() + note("C", accent),
    ])
    #expect(velocities(s) == [79, 95, 111, 79, 127, 47, 47, 63])
    #expect(s.parts[0].notes.map(\.accent) == [0, 1, 2, 0, 2, 0, 0, 1])
    #expect(s.parts[0].dynamics[4 * 960 + 960] == "p")
    // percussion follows the dynamics too
    let drums = try part([dyn("pp") + "<note><unpitched><display-step>C</display-step><display-octave>5</display-octave></unpitched><duration>4</duration></note>"],
                         percussion: true)
    #expect(velocities(drums) == [31])
}

/// A crescendo from p to ff over a bar rises linearly to ff where it stops.
@Test func crescendoInterpolatesToTheNextMark() throws {
    let s = try part([
        dyn("p") + wedge("crescendo") + note() + note() + note() + note(),
        wedge("stop") + dyn("ff") + note() + note() + note() + note(),
    ])
    #expect(s.parts[0].wedges == [Wedge(kind: .crescendo, startTick: 0, stopTick: 3840)])
    // 47 → 111 over four beats: 47, 63, 79, 95, then ff
    #expect(velocities(s) == [47, 63, 79, 95, 111, 111, 111, 111])
}

/// A diminuendo with no mark at its end falls one step and stays there until the next mark.
@Test func diminuendoWithoutAnEndMarkFallsOneStep() throws {
    let s = try part([
        dyn("f") + note() + wedge("diminuendo") + note() + note() + wedge("stop") + note(),
        note() + note() + note() + note(),
        note() + note() + dyn("f") + note() + note(),
    ])
    #expect(s.parts[0].wedges == [Wedge(kind: .diminuendo, startTick: 960, stopTick: 2880)])
    #expect(velocities(s) == [95, 95, 87, 79, 79, 79, 79, 79, 79, 79, 95, 95])
}

/// Numbered hairpins overlap independently; an unterminated one is dropped.
@Test func wedgesPairByNumber() throws {
    let s = try part([
        "<direction><direction-type><wedge type=\"crescendo\" number=\"1\"/></direction-type></direction>" + note()
            + "<direction><direction-type><wedge type=\"diminuendo\" number=\"2\"/></direction-type></direction>" + note()
            + "<direction><direction-type><wedge type=\"stop\" number=\"1\"/></direction-type></direction>" + note() + wedge("crescendo") + note(),
    ])
    #expect(s.parts[0].wedges == [Wedge(kind: .crescendo, startTick: 0, stopTick: 1920)])
}

/// The golden arrangement plays alphaTab's velocities: only table values, and its opening p.
@Test(.enabled(if: goldenDir() != nil)) func goldenPlaysItsDynamics() throws {
    let score = try MusicXMLParser.parse(url: try #require(goldenDir()).appending(path: "brass-band.musicxml"))
    let all = score.parts.flatMap(\.playbackNotes).map(\.velocity)
    #expect(Set(all).isSubset(of: [31, 47, 63, 79, 95, 111]))
    let solo = try #require(score.parts.first { $0.name == "Solo Cornet" })
    #expect(solo.playbackNotes.first?.velocity == 47)
    // mostly f and ff, as alphaTab plays it (95 and 111 on 80 % of the notes)
    let loud = all.filter { $0 >= 95 }.count
    #expect(Double(loud) / Double(all.count) > 0.75)
}
