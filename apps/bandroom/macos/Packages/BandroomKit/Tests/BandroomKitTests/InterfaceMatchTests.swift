import Testing
@testable import BandroomKit

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
}
