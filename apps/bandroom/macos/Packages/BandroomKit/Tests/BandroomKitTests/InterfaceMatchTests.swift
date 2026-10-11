import Foundation
import Testing
@testable import BandroomKit

let enginesWirePath = "engine/src/scribe_engine/wire.py"

/// The repository this package sits in, found from this file by the engine's `wire.py`; nil outside a checkout of the
/// whole repository.
func repository() -> URL? {
    var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<10 {
        if FileManager.default.fileExists(atPath: dir.appending(path: enginesWirePath).path) { return dir }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

/// The tests that read the engine's file are skipped outside a checkout of the whole repository, but never in CI: there
/// a file that has moved fails them.
let enginesWireIsRead = repository() != nil || ProcessInfo.processInfo.environment["CI"] != nil

/// `NAME = value` in the engine's `wire.py`, without the quotes.
func enginesWire(_ name: String) throws -> String {
    let root = try #require(repository(), "\(enginesWirePath) was not found above this file")
    let wire = try String(contentsOf: root.appending(path: enginesWirePath), encoding: .utf8)
    let found = wire.firstMatch(of: try Regex("(?m)^\(name)\\s*=\\s*\"?([^\"\\s#]+)\"?"))?.output[1].substring.map(String.init)
    return try #require(found, "\(name) is not in \(enginesWirePath)")
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
    @Test(.enabled(if: enginesWireIsRead)) func theInterfaceVersionIsTheEngines() throws {
        #expect(try enginesWire("INTERFACE_VERSION") == String(Wire.interfaceVersion))
    }

    /// The network service the engine advertises is the one the app's Info.plist lets it use on the local network, and
    /// the project file the plist is made from says the same. (Bandroom has no pairing link of its own: the engine
    /// makes it.)
    @Test(.enabled(if: enginesWireIsRead)) func theAppsInfoCarriesTheEnginesService() throws {
        let service = try enginesWire("SERVICE_TYPE")
        let app = try #require(repository()).appending(path: "apps/bandroom/macos")
        let data = try Data(contentsOf: app.appending(path: "App/Info.plist"))
        let info = try #require(try PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any])
        #expect(info["NSBonjourServices"] as? [String] == [service])
        #expect((info["CFBundleURLTypes"] as? [Any] ?? []).isEmpty)
        let project = try String(contentsOf: app.appending(path: "project.yml"), encoding: .utf8)
        let listed = project.matches(of: /(?m)^\s*NSBonjourServices:\s*\[([^\]]*)\]/).map { $0.output.1.trimmingCharacters(in: .whitespaces) }
        #expect(listed == [service])
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
