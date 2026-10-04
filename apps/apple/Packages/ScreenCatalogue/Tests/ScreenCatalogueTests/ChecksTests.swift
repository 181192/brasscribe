import AppKit
import Testing
@testable import ScreenCatalogue

/// The checks' rules on frames given by hand. The apps' catalogues show them on views drawn to fail them.
@MainActor
struct ChecksTests {
    private func button(_ name: String, _ x: CGFloat, _ y: CGFloat, _ w: CGFloat = 80, _ h: CGFloat = 28, role: String = "AXButton") -> AXNode {
        AXNode(role: role, label: name, frame: CGRect(x: x, y: y, width: w, height: h))
    }

    @Test func anOwnButtonUnder24PointsIsSmallWhereverItIs() {
        let more = button("More", 300, 10, 20, 14)
        #expect(Checks.isSmall(more, among: [more]))
    }

    @Test func aStandardControlUnder24PointsPassesWithRoomAroundIt() {
        let radio = button("Dark", 20, 100, 420, 16, role: "AXRadioButton")
        let other = button("Light", 20, 137, 420, 16, role: "AXRadioButton")
        #expect(!Checks.isSmall(radio, among: [radio, other]))
        let crowded = button("Lighter", 20, 110, 420, 16, role: "AXRadioButton")
        #expect(Checks.isSmall(radio, among: [radio, crowded]))
    }

    @Test func aControlAfterOneBelowItIsOutOfOrder() {
        #expect(Checks.order([button("Lower", 10, 100), button("Upper", 10, 20)]).count == 1)
        #expect(Checks.order([button("Right", 200, 20), button("Left", 10, 20)]).count == 1)
        #expect(Checks.order([button("Top", 10, 20), button("Left", 10, 100), button("Right", 200, 100)]).isEmpty)
    }

    @Test func aLineCutWithAnEllipsisIsFoundAndOneThatFitsIsNot() {
        let fit = TextFit()
        let words = "Without it, Brasscribe can't write down a full band. You can add it later."
        // one line of 17 pt (21 pt high) in 342 pt: the words need about 530
        #expect(fit.isCut(words, in: CGRect(x: 0, y: 0, width: 342, height: 21)))
        #expect(!fit.isCut(words, in: CGRect(x: 0, y: 0, width: 560, height: 21)))
        // three lines, as wide as the widest of them: not called cut
        #expect(!fit.isCut(words, in: CGRect(x: 0, y: 0, width: 230, height: 63)))
    }

    @Test func aControlWithoutANameAndTextOutsideTheWindowAreFound() {
        let nodes = [button("", 10, 10, 30, 30), AXNode(role: "AXStaticText", label: "", value: "Below", frame: CGRect(x: 10, y: 190, width: 60, height: 20))]
        let found = Checks.run(nodes, bounds: CGRect(x: 0, y: 0, width: 200, height: 200), text: TextFit())
        #expect(found.contains { $0.kind == .unlabelled })
        #expect(found.contains { $0.kind == .outsideWindow })
    }
}
