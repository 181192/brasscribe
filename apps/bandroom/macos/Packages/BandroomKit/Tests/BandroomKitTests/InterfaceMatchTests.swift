import Foundation
import Testing
@testable import BandroomKit

/// `engine/src/scribe_engine/wire.py`, found from this file; nil outside a checkout of the whole repository.
func engineWire() -> String? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        if let text = try? String(contentsOf: dir.appending(path: "engine/src/scribe_engine/wire.py"), encoding: .utf8) { return text }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

@Suite struct InterfaceMatchTests {
    @Test func sameNumberIsAMatch() {
        #expect(InterfaceMatch.of(engine: 3, app: 3) == .match)
        #expect(InterfaceMatch.of(engine: 3, app: 3).behind == nil)
        #expect(InterfaceMatch.of(engine: Wire.interfaceVersion) == .match)
    }

    @Test func aNewerEngineMeansBandroomIsBehind() {
        #expect(InterfaceMatch.of(engine: 4, app: 3) == .mismatch(.bandroom))
        #expect(InterfaceMatch.of(engine: 4, app: 3).behind == .bandroom)
    }

    @Test func anOlderEngineIsBehind() {
        #expect(InterfaceMatch.of(engine: 2, app: 3) == .mismatch(.engine))
    }

    /// An engine from before the number says none.
    @Test func anEngineWithoutANumberIsBehind() {
        #expect(InterfaceMatch.of(engine: nil, app: 3) == .mismatch(.engine))
        #expect(InterfaceMatch.of(engine: nil) == .mismatch(.engine))
    }

    /// Bandroom's number is the engine's own: a change to one without the other fails here.
    @Test(.enabled(if: engineWire() != nil)) func theInterfaceVersionIsTheEngines() throws {
        let wire = try #require(engineWire())
        let number = wire.firstMatch(of: /(?m)^INTERFACE_VERSION\s*=\s*(\d+)\s*$/).map { String($0.output.1) }
        #expect(number == String(Wire.interfaceVersion))
    }

    /// A number that is not a whole number reads as none (the engine is behind), and the rest of health still reads.
    @Test(arguments: ["1.5", "true", "\"1\"", "null", "99999999999999999999", "[1]"])
    func aHealthAnswerWithANumberThatIsNotWholeStillReads(number: String) throws {
        let body = #"{"status":"ok","version":"0.9.4","device":"mps","auth_required":false,"server_id":"3f9c","server_name":"Brasscribe on X","interface_version":\#(number)}"#
        let h = try JSONDecoder().decode(Health.self, from: Data(body.utf8))
        #expect(h.interfaceVersion == nil && h.serverId == "3f9c")
        #expect(InterfaceMatch.of(engine: h.interfaceVersion) == .mismatch(.engine))
    }

    // MARK: what Bandroom offers to do about it

    static let installed = EngineSource.installed(workspace: URL(fileURLWithPath: "/tmp/envs/brasscribe"), adapters: nil)
    static let checkout = EngineSource.checkout(URL(fileURLWithPath: "/tmp/checkout"))

    @Test func anOlderBandroomIsFixedByANewerOne() {
        for source in [Self.installed, Self.checkout] {
            for (current, tried) in [(false, false), (true, false), (false, true), (true, true)] {
                #expect(MismatchFix.of(behind: .bandroom, source: source, engineIsThisApps: current, updateTried: tried) == .getBandroom)
            }
        }
    }

    @Test func anInstalledEngineThatIsBehindIsUpdatedOnce() {
        #expect(MismatchFix.of(behind: .engine, source: Self.installed, engineIsThisApps: false, updateTried: false) == .updateEngine)
        // updating would put the same engine back: only a newer Bandroom has a newer one
        #expect(MismatchFix.of(behind: .engine, source: Self.installed, engineIsThisApps: true, updateTried: false) == .getBandroom)
        #expect(MismatchFix.of(behind: .engine, source: Self.installed, engineIsThisApps: false, updateTried: true) == .getBandroom)
        #expect(MismatchFix.of(behind: .engine, source: Self.installed, engineIsThisApps: true, updateTried: true) == .getBandroom)
    }

    /// Bandroom does not update a developer's checkout, so it offers nothing that would do nothing.
    @Test func anEngineFromACheckoutIsNotBandroomsToUpdate() {
        for (current, tried) in [(false, false), (true, false), (false, true), (true, true)] {
            #expect(MismatchFix.of(behind: .engine, source: Self.checkout, engineIsThisApps: current, updateTried: tried) == .none)
        }
    }
}
