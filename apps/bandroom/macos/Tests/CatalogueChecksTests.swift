import AppKit
import ScreenCatalogue
import SwiftUI
import Testing
@testable import Brasscribe_Bandroom

/// The catalogue's checks find what they should: each on a view made to fail it, and none on one made right.
@MainActor
@Suite(.serialized) struct CatalogueChecksTests {
    private func findings(_ view: some View, width: CGFloat = 360) async -> [Finding] {
        let app = await Catalogue.model(busy: false)
        let r = await Rendering(view.padding(14), width: width, variant: .light, app: app)
        defer { r.close() }
        let nodes = AXTree.read(r.hosting)
        if let broken = Guards.tree(nodes, screen: "checks") { Issue.record(Comment(rawValue: broken)) }
        return Checks.run(nodes, bounds: r.hosting.bounds, text: Catalogue.text)
    }

    @Test func aRightViewHasNoFindings() async {
        let found = await findings(VStack(alignment: .leading, spacing: 12) {
            Text("A heading").font(.title2).accessibilityAddTraits(.isHeader)
            Text("Words that wrap onto a second line when the window is narrow, as they should.").fixedSize(horizontal: false, vertical: true)
            HStack { Button("First") {}.controlSize(.large); Button("Second") {}.controlSize(.large) }
        })
        #expect(found.isEmpty, "\(found)")
    }

    @Test func aSmallButtonIsFound() async {
        let found = await findings(VStack {
            Button {} label: { Image(systemName: "ellipsis") }.buttonStyle(.plain).accessibilityLabel(Text("More"))
            Button("Big enough") {}.controlSize(.large)
        })
        #expect(found.contains { $0.kind == .smallTarget && $0.node.contains("More") }, "\(found)")
    }

    @Test func aButtonWithoutANameIsFound() async {
        let found = await findings(VStack {
            Button {} label: { Circle().frame(width: 30, height: 30) }.buttonStyle(.plain)
            Button("Named") {}.controlSize(.large)
        })
        #expect(found.contains { $0.kind == .unlabelled }, "\(found)")
    }

    @Test func textCutOffIsFound() async {
        let found = await findings(VStack(alignment: .leading) {
            Text("Without it, Brasscribe can't write down a full band. You can add it later.").font(.system(size: 17)).lineLimit(1)
            Button("Continue") {}.controlSize(.large)
        }, width: 300)
        #expect(found.contains { $0.kind == .clippedText && $0.node.contains("Without it") }, "\(found)")
    }

    @Test func controlsOutOfReadingOrderAreFound() async {
        // The lower one is read first.
        let found = await findings(VStack {
            Button("Upper") {}.controlSize(.large).accessibilitySortPriority(0)
            Button("Lower") {}.controlSize(.large).accessibilitySortPriority(1)
        }.accessibilityElement(children: .contain))
        let order = await findings(VStack {
            Button("Top") {}.controlSize(.large)
            Button("Bottom") {}.controlSize(.large)
        })
        #expect(found.contains { $0.kind == .outOfOrder }, "\(found)")
        #expect(!order.contains { $0.kind == .outOfOrder }, "\(order)")
    }
}
