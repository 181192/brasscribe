import Foundation
import Testing
@testable import TabKit

/// Defaults of a test's own.
final class TestDefaults {
    let name = "tabkit-\(UUID().uuidString)"
    let defaults: UserDefaults
    init(_ values: [String: String] = [:]) {
        defaults = UserDefaults(suiteName: name)!
        for (k, v) in values { defaults.set(v, forKey: k) }
    }
    deinit { defaults.removePersistentDomain(forName: name) }
    var keys: Set<String> { Set(defaults.persistentDomain(forName: name).map { Array($0.keys) } ?? []) }
}

let presetsSource = repositoryRoot.appending(path: "core/targets/fretted/src/instrument.rs")

/// "Your instrument": the defaults, what can be chosen, what a job is asked for, and the stored answer.
struct YourInstrumentTests {
    /// Every instrument, kind and tuning the screen offers.
    let offered: [(FrettedInstrument, String)] = Instrument.allCases.flatMap { i in i.kinds.flatMap { kind in kind.tunings.map { (kind, $0) } } }

    @Test func notNowIsASixStringGuitarInStandardTuningReadAsTab() {
        let d = YourInstrument.default
        #expect(d.instrument == .guitar)
        #expect(d.kind == .guitar6)
        #expect(d.strings == 6)
        #expect(d.tuning == "standard")
        #expect(d.hand == .left)
        #expect(d.reads == .tab)
        #expect(d.jobOptions() == TabJobOptions(instrument: "guitar-6", tuning: "standard", layout: "tab"))
        // Nothing stored reads as the same.
        let store = TestDefaults()
        #expect(YourInstrumentStore(store.defaults).load() == d)
    }

    @Test func everyInstrumentCanBeChosenWithItsKinds() {
        #expect(Instrument.allCases == [.guitar, .bass, .ukulele, .mandolin])
        #expect(Instrument.guitar.kinds.map(\.id) == ["guitar-6", "guitar-7", "guitar-8"])
        #expect(Instrument.bass.kinds.map(\.id) == ["bass-4", "bass-5", "bass-6"])
        // Soprano, concert and tenor are one kind; the baritone is another.
        #expect(Instrument.ukulele.kinds.map(\.id) == ["ukulele", "ukulele-baritone"])
        #expect(Instrument.mandolin.kinds.map(\.id) == ["mandolin"])
        // Every instrument the computer writes tab for is offered, once.
        let kinds = Instrument.allCases.flatMap(\.kinds)
        #expect(Set(FrettedInstrument.allCases) == Set(kinds))
        #expect(kinds.count == Set(kinds).count)
        for kind in kinds { #expect(Instrument.of(kind).kinds.contains(kind)) }
        // A guitar and a bass are chosen by their strings; a ukulele by its size; a mandolin comes in one kind.
        #expect((Instrument.guitar.kinds + Instrument.bass.kinds).map(YourInstrument.stringsOf) == [6, 7, 8, 4, 5, 6])
        for kind in Instrument.ukulele.kinds + Instrument.mandolin.kinds { #expect(YourInstrument.stringsOf(kind) == nil) }
        // A capo is asked about for a guitar and a ukulele.
        #expect(Instrument.allCases.filter(\.takesCapo) == [.guitar, .ukulele])
    }

    @Test func theTuningsOfEachInstrumentAreTheOnesTheComputerHasItsUsualOneFirst() {
        func tunings(_ kind: FrettedInstrument) -> [String] { YourInstrument(kind).tunings }
        #expect(tunings(.guitar6) == ["standard", "eb-standard", "d-standard", "c-standard", "drop-d", "drop-c", "drop-b", "dadgad", "open-g", "open-d", "open-e"])
        #expect(tunings(.guitar7) == ["standard", "eb-standard"])
        #expect(tunings(.guitar8) == ["standard"])
        #expect(tunings(.bass4) == ["standard", "eb-standard", "d-standard", "drop-d", "bead"])
        #expect(tunings(.bass5) == ["standard", "drop-a"])
        #expect(tunings(.bass6) == ["standard"])
        #expect(tunings(.ukulele) == ["high-g", "low-g"])
        #expect(tunings(.ukuleleBaritone) == ["standard"])
        #expect(tunings(.mandolin) == ["standard"])
        // A new answer starts in the instrument's usual tuning: a ukulele's is high G, not "standard".
        for kind in Instrument.allCases.flatMap(\.kinds) { #expect(YourInstrument(kind).tuning == kind.tunings.first) }
        #expect(YourInstrument(.ukulele).tuning == "high-g")
    }

    @Test func everyInstrumentTuningAndLayoutMapsToItsJobOptions() {
        let layouts: [Reads: String] = [.tab: "tab", .tabAndNotation: "tab-and-notation", .notation: "notation"]
        #expect(Set(Reads.allCases) == Set(layouts.keys))
        var seen = 0
        for (kind, tuning) in offered {
            for (reads, layout) in layouts {
                for hand in FrettingHand.allCases {
                    let chosen = YourInstrument(kind, tuning: tuning, hand: hand, reads: reads)
                    #expect(chosen.valid() == chosen)
                    // The hand is for the screens that draw a neck: it never reaches the job.
                    #expect(chosen.jobOptions() == TabJobOptions(instrument: kind.id, tuning: tuning, layout: layout))
                    #expect(chosen.family == kind.id)
                    #expect(chosen.preset == kind.preset(tuning))
                    seen += 1
                }
            }
        }
        #expect(seen == (11 + 2 + 1 + 5 + 2 + 1 + 2 + 1 + 1) * 3 * 3)
        #expect(YourInstrument(.guitar6, tuning: "drop-d").preset == "guitar-drop-d")
        #expect(YourInstrument(.ukuleleBaritone).preset == "ukulele-baritone")
        #expect(YourInstrument(.mandolin).preset == "mandolin")
    }

    @Test(.enabled(if: FileManager.default.fileExists(atPath: presetsSource.path), "core/targets/fretted is not in this checkout"))
    func theTuningsAreTheCratesPresets() throws {
        let source = try String(contentsOf: presetsSource, encoding: .utf8)
        let start = try #require(source.range(of: "pub const PRESET_IDS: &[&str] = &["))
        let end = try #require(source.range(of: "];", range: start.upperBound..<source.endIndex))
        let list = String(source[start.upperBound..<end.lowerBound])
        let crate = try NSRegularExpression(pattern: #""([^"]+)""#).matches(in: list, range: NSRange(list.startIndex..., in: list))
            .map { String(list[Range($0.range(at: 1), in: list)!]) }
        #expect(!crate.isEmpty)
        // In the crate's order: the guitars, the basses, the ukuleles, the mandolin, each kind's usual tuning first.
        #expect(crate == offered.map { YourInstrument($0.0, tuning: $0.1).preset })
    }

    @Test func changingTheKindKeepsATuningTheNewOneHas() {
        let dropD = YourInstrument(.bass4, tuning: "drop-d")
        #expect(dropD.withKind(.bass5) == YourInstrument(.bass5, tuning: "standard"))
        #expect(YourInstrument(.bass5, tuning: "drop-a").withKind(.bass4) == YourInstrument(.bass4, tuning: "standard"))
        #expect(YourInstrument(.bass5).withKind(.bass6) == YourInstrument(.bass6))
        #expect(YourInstrument(.guitar6, tuning: "eb-standard").withKind(.guitar7) == YourInstrument(.guitar7, tuning: "eb-standard"))
        #expect(YourInstrument(.guitar6, tuning: "dadgad").withKind(.guitar7) == YourInstrument(.guitar7, tuning: "standard"))
        // A baritone has no high or low G; back on the smaller ones the usual tuning is high G.
        let baritone = YourInstrument(.ukulele, tuning: "low-g").withKind(.ukuleleBaritone)
        #expect(baritone == YourInstrument(.ukuleleBaritone, tuning: "standard"))
        #expect(baritone.withKind(.ukulele) == YourInstrument(.ukulele, tuning: "high-g"))
        // The hand and what is read stay.
        let mine = YourInstrument(.guitar6, tuning: "drop-d", hand: .right, reads: .notation)
        #expect(mine.withKind(.guitar8) == YourInstrument(.guitar8, tuning: "standard", hand: .right, reads: .notation))
    }

    @Test func anotherInstrumentStartsInItsOwnUsualTuning() {
        let mine = YourInstrument(.guitar6, tuning: "drop-d", hand: .right, reads: .tabAndNotation)
        // A four-string bass has a drop D too, but the player has not said the bass is in it.
        #expect(mine.withInstrument(.bass) == YourInstrument(.bass4, tuning: "standard", hand: .right, reads: .tabAndNotation))
        #expect(mine.withInstrument(.ukulele) == YourInstrument(.ukulele, tuning: "high-g", hand: .right, reads: .tabAndNotation))
        #expect(mine.withInstrument(.mandolin) == YourInstrument(.mandolin, tuning: "standard", hand: .right, reads: .tabAndNotation))
        // The same instrument again changes nothing.
        #expect(mine.withInstrument(.guitar) == mine)
        let seven = YourInstrument(.guitar7, tuning: "eb-standard")
        #expect(seven.withInstrument(.guitar) == seven)
        for i in Instrument.allCases { #expect(mine.withInstrument(i).instrument == i) }
    }

    @Test func theAnswerComesBackAsItWasSaved() {
        let store = TestDefaults()
        for (kind, tuning) in offered {
            for hand in FrettingHand.allCases {
                for reads in Reads.allCases {
                    let chosen = YourInstrument(kind, tuning: tuning, hand: hand, reads: reads)
                    YourInstrumentStore(store.defaults).save(chosen)
                    // A new store on the same defaults: what the next start of the app reads.
                    #expect(YourInstrumentStore(UserDefaults(suiteName: store.name)!).load() == chosen)
                }
            }
        }
        #expect(store.keys == [YourInstrumentStore.kindKey, YourInstrumentStore.tuningKey, YourInstrumentStore.handKey, YourInstrumentStore.readsKey])
    }

    @Test func savingLeavesEverythingElseInTheDefaultsAlone() {
        let store = TestDefaults(["appearance": "dark", "other-setting": "kept"])
        YourInstrumentStore(store.defaults).save(YourInstrument(.bass5, tuning: "drop-a", hand: .right))
        #expect(store.defaults.string(forKey: "appearance") == "dark")
        #expect(store.defaults.string(forKey: "other-setting") == "kept")
    }

    @Test func storedValuesThisVersionCantOfferReadAsTheDefaults() {
        func load(_ stored: [String: String]) -> YourInstrument {
            let store = TestDefaults(stored)
            return YourInstrumentStore(store.defaults).load()
        }
        let d = YourInstrument.default
        let (kind, tuning, hand, reads) = (YourInstrumentStore.kindKey, YourInstrumentStore.tuningKey, YourInstrumentStore.handKey, YourInstrumentStore.readsKey)
        // An instrument this version has never heard of.
        #expect(load([kind: "banjo-5"]) == d)
        #expect(load([kind: "banjo-5", tuning: "open-g"]) == d)
        // A tuning the instrument has no preset for is its usual one; the instrument stays.
        #expect(load([kind: "bass-5", tuning: "drop-d"]) == YourInstrument(.bass5))
        #expect(load([kind: "ukulele", tuning: "standard"]) == YourInstrument(.ukulele, tuning: "high-g"))
        #expect(load([kind: "mandolin", tuning: "dadgad"]) == YourInstrument(.mandolin))
        #expect(load([kind: "ukulele"]) == YourInstrument(.ukulele))
        // An unknown hand or reading is the default; the rest of the answer stays.
        var dadgad = d
        dadgad.tuning = "dadgad"
        #expect(load([kind: "guitar-6", tuning: "dadgad", hand: "both", reads: "braille"]) == dadgad)
        // A tuning with no instrument beside it says nothing.
        #expect(load([tuning: "dadgad"]) == d)
        #expect(load([hand: "right-upside-down", reads: "notation"]) == YourInstrument(hand: .rightUpsideDown, reads: .notation))
    }

    @Test func anAnswerThatCantBeChosenNeverReachesAJobOrTheStore() {
        // A tuning of another instrument: the instrument's usual one is asked for.
        #expect(YourInstrument(.ukulele, tuning: "drop-d").jobOptions() == TabJobOptions(instrument: "ukulele", tuning: "high-g", layout: "tab"))
        #expect(YourInstrument(.bass6, tuning: "bead").jobOptions() == TabJobOptions(instrument: "bass-6", tuning: "standard", layout: "tab"))
        #expect(YourInstrument(.bass6, tuning: "bead").preset == "bass-6-standard")
        let store = TestDefaults()
        YourInstrumentStore(store.defaults).save(YourInstrument(.mandolin, tuning: "dadgad", hand: .right, reads: .notation))
        #expect(store.defaults.string(forKey: YourInstrumentStore.tuningKey) == "standard")
    }
}
