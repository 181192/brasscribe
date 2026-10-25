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
        // a footer docked over a scroll area, after content that has scrolled below it; but not before content
        let content = AXNode(role: "AXCheckBox", label: "Show", frame: CGRect(x: 10, y: 300, width: 56, height: 26), inScrollArea: true)
        let footer = button("Cancel", 10, 240)
        #expect(Checks.order([content, footer]).isEmpty)
        #expect(Checks.order([footer, AXNode(role: "AXButton", label: "Top", frame: CGRect(x: 10, y: 20, width: 80, height: 28), inScrollArea: true)]).count == 1)
        // from the bottom of a sidebar to the top of the content beside it
        #expect(Checks.order([button("Sidebar", 10, 400), button("Content", 300, 20)]).isEmpty)
    }

    @Test func aLineCutWithAnEllipsisIsFoundAndOneThatFitsIsNot() {
        let fit = TextFit()
        let words = "Without it, Brasscribe can't write down a full band. You can add it later."
        // one line of 17 pt (21 pt high) in 342 pt: the words need about 530
        #expect(fit.isCut(words, in: CGRect(x: 0, y: 0, width: 342, height: 21)))
        #expect(!fit.isCut(words, in: CGRect(x: 0, y: 0, width: 560, height: 21)))
        // three lines, as wide as the widest of them: not called cut
        #expect(!fit.isCut(words, in: CGRect(x: 0, y: 0, width: 230, height: 63)))
        // one line with room around it (48 pt high): not taken for one line of 40 pt
        #expect(!fit.isCut("A file you own, or a recording with the microphone, always works.", in: CGRect(x: 0, y: 0, width: 680, height: 48)))
    }

    @Test func whatAScrollAreaHasOutOfViewIsNotOutsideTheWindow() {
        let below = AXNode(role: "AXButton", label: "Below", frame: CGRect(x: 10, y: 300, width: 80, height: 28), inScrollArea: true)
        #expect(Checks.run([below], bounds: CGRect(x: 0, y: 0, width: 200, height: 200), text: TextFit()).isEmpty)
    }

    /// The player's bar under a score: the score's bars go on under it, out of their scroll area's view.
    @Test func whatAnotherScrollAreaHasOutOfViewDoesNotCrowdAStandardControl() {
        let score = CGRect(x: 0, y: 0, width: 600, height: 400), bar = CGRect(x: 0, y: 400, width: 600, height: 100)
        let window = CGRect(x: 0, y: 0, width: 600, height: 500)
        let slider = AXNode(role: "AXSlider", label: "Speed", frame: CGRect(x: 70, y: 440, width: 140, height: 16), viewport: bar)
        let hidden = AXNode(role: "AXButton", label: "Bar 9", frame: CGRect(x: 100, y: 436, width: 200, height: 50), viewport: score)
        #expect(hidden.isOutOfView)
        #expect(!Checks.run([hidden, slider], bounds: window, text: TextFit()).contains { $0.kind == .smallTarget })
        // in view in the same scroll area, it is beside the slider
        let shown = AXNode(role: "AXButton", label: "Slower", frame: CGRect(x: 100, y: 458, width: 80, height: 28), viewport: bar)
        #expect(Checks.run([slider, shown], bounds: window, text: TextFit()).contains { $0.kind == .smallTarget })
        // and one of the app's own buttons is small wherever the others are
        let more = AXNode(role: "AXButton", label: "More", frame: CGRect(x: 300, y: 440, width: 20, height: 14), viewport: bar)
        #expect(Checks.run([hidden, more], bounds: window, text: TextFit()).contains { $0.kind == .smallTarget })
    }

    @Test func aControlWithoutANameAndTextOutsideTheWindowAreFound() {
        let nodes = [button("", 10, 10, 30, 30), AXNode(role: "AXStaticText", label: "", value: "Below", frame: CGRect(x: 10, y: 190, width: 60, height: 20))]
        let found = Checks.run(nodes, bounds: CGRect(x: 0, y: 0, width: 200, height: 200), text: TextFit())
        #expect(found.contains { $0.kind == .unlabelled })
        #expect(found.contains { $0.kind == .outsideWindow })
    }
}
