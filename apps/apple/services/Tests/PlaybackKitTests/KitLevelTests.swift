import AVFoundation
import Foundation
import Testing
import ScoreKit
@testable import PlaybackKit

/// The band kit levelled drum by drum (band.apple_kit_trim_db): drums in groups within 2 dB, one sampler and one
/// sequencer track per group.
private let drums = """
<?xml version="1.0"?><score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Percussion</part-name>
<score-instrument id="K36"><instrument-name>Bass Drum</instrument-name></score-instrument>
<score-instrument id="K42"><instrument-name>Closed Hi-Hat</instrument-name></score-instrument>
<score-instrument id="K54"><instrument-name>Tambourine</instrument-name></score-instrument>
<midi-instrument id="K36"><midi-channel>10</midi-channel><midi-unpitched>37</midi-unpitched></midi-instrument>
<midi-instrument id="K42"><midi-channel>10</midi-channel><midi-unpitched>43</midi-unpitched></midi-instrument>
<midi-instrument id="K54"><midi-channel>10</midi-channel><midi-unpitched>55</midi-unpitched></midi-instrument>
</score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions>
<time><beats>3</beats><beat-type>4</beat-type></time><clef><sign>percussion</sign></clef></attributes>
<note><unpitched><display-step>F</display-step><display-octave>4</display-octave></unpitched><duration>1</duration><instrument id="K36"/><type>quarter</type></note>
<note><unpitched><display-step>G</display-step><display-octave>5</display-octave></unpitched><duration>1</duration><instrument id="K42"/><type>quarter</type><notehead>x</notehead></note>
<note><unpitched><display-step>B</display-step><display-octave>5</display-octave></unpitched><duration>1</duration><instrument id="K54"/><type>quarter</type><notehead>x</notehead></note>
</measure></part></score-partwise>
"""

@Test func drumsPlayTheirMidiUnpitchedKey() throws {
    let s = try MusicXMLParser.parse(Data(drums.utf8))
    // the tambourine's position (B5, x) is not in the arranger's drum map; its <midi-unpitched> 55 is key 54
    #expect(s.parts[0].playbackNotes.map(\.pitch) == [36, 42, 54])
}

@Test func kitGroupsStayWithinTwoDecibels() {
    for program in [0, 1] {
        let g = PlaybackLevels.kitGroups(program: program)
        for key in PlaybackLevels.appleKitTrimDB.keys {
            let t = PlaybackLevels.kitTrimDB(key, program: program)!
            #expect(abs(g.trimDB[g.of(key)] - t) <= PlaybackLevels.kitGroupSpanDB / 2 + 0.05, "key \(key), kit \(program)")
        }
        #expect(g.trimDB.count <= 16)
    }
    // the pop kit's crashes are MS Basic's own, 12-16 dB hotter on the sampler than the band kit's
    #expect(PlaybackLevels.kitTrimDB(49, program: 1)! < PlaybackLevels.kitTrimDB(49, program: 0)! - 10)
    #expect(PlaybackLevels.kitTrimDB(36, program: 1) == PlaybackLevels.kitTrimDB(36, program: 0))
}

@Test func eachDrumGroupGetsATrackOfItsOwn() throws {
    let s = try MusicXMLParser.parse(Data(drums.utf8))
    let kit = PlaybackLevels.kitGroups(program: 0)
    let o = MIDIWriter.Options(includeMetronome: true, drumGroup: { kit.of($0) })
    let groups = try #require(MIDIWriter.drumGroups(for: s, options: o)["P1"])
    #expect(groups == Set([36, 42, 54].map { kit.of($0) }).sorted())
    #expect(MIDIWriter.drumGroupTracks(for: s, options: o).map(\.group) == Array(groups.dropFirst()))
    // conductor, the part, the metronome, then one track per further group
    let seq = AVAudioSequencer()
    try seq.load(from: MIDIWriter.data(for: s, options: o), options: [])
    #expect(seq.tracks.count >= 2 + groups.count)
}
