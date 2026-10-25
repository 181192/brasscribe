import Foundation
import Testing
import TranscriptionKit
@testable import BrasscribePlay

/// Engine and core failures in the player's words, never the engine's own English text.
@Test func engineCodesHaveTheirOwnWords() {
    #expect(ErrorWords.engineCode(#"{"code": "seat_no_tune", "detail": "the E♭ Bass does not carry the tune"}"#) == "seat_no_tune")
    // a body cut short after 300 bytes still starts with its code
    #expect(ErrorWords.engineCode(#"{"code":"percussion_solo","detail":"percussion can't be wri"#) == "percussion_solo")
    #expect(ErrorWords.engineCode("Internal Server Error") == nil)
    let percussion = TranscriptionError.http(422, #"{"code": "percussion_solo", "detail": "x"}"#)
    #expect(ErrorWords.plain(percussion) == Seats.percussionSoloRefused)
    #expect(ErrorWords.plain(TranscriptionError.http(422, #"{"code": "quartet_needs_group", "detail": "x"}"#)) == "Needs a recording of the whole group")
    #expect(ErrorWords.specific(TranscriptionError.http(422, "old engine")) != nil)
    #expect(ErrorWords.specific(TranscriptionError.http(500, "boom"))?.contains("couldn't finish") == true)
    #expect(ErrorWords.specific(TranscriptionError.unreachable("refused"))?.hasPrefix("Can't reach") == true)
    #expect(ErrorWords.specific(URLError(.timedOut))?.contains("too long") == true)
    #expect(ErrorWords.specific(TranscriptionError.jobFailed("MuseScore did not write brass-band.pdf"))?.contains("MuseScore") == false)
    #expect(ErrorWords.specific(CocoaError(.fileReadCorruptFile)) == nil)
    #expect(ErrorWords.plain(CocoaError(.fileReadCorruptFile)) == "Something went wrong. Try again.")
}
