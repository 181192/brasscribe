import CoreText
import Foundation
import SwiftUI
import Testing
@testable import BrasscribePlay

/// The design system is linked from design/dist. These fail when a colour set, the display
/// face or the app icon silently goes missing from the bundle.
@Suite struct DesignSystemTests {
    @Test(arguments: ["bg", "text", "primary", "onPrimary", "uncertain", "veryUncertain", "cursor", "cursorTint", "loopTint", "adlibTint"])
    func colourSetIsInTheBundle(_ name: String) {
        #if os(iOS)
        #expect(UIColor(named: "Brasscribe/\(name)", in: ScribeDesign.bundle, compatibleWith: nil) != nil)
        #else
        #expect(NSColor(named: "Brasscribe/\(name)", bundle: ScribeDesign.bundle) != nil)
        #endif
    }

    @Test(arguments: ["InstrumentSerif-Regular", "InstrumentSerif-Italic"])
    func displayFaceIsRegistered(_ postScriptName: String) {
        let font = CTFontCreateWithName(postScriptName as CFString, 28, nil)
        #expect(CTFontCopyPostScriptName(font) as String == postScriptName)
    }

    @Test func appIconIsCompiled() {
        #if os(iOS)
        let icons = Bundle.main.object(forInfoDictionaryKey: "CFBundleIcons") as? [String: Any]
        let primary = icons?["CFBundlePrimaryIcon"] as? [String: Any]
        #expect(primary?["CFBundleIconName"] as? String == "AppIcon")
        #else
        #expect(Bundle.main.object(forInfoDictionaryKey: "CFBundleIconName") as? String == "AppIcon")
        #endif
    }

    /// The neutral names (design/tokens/README.md) are the same in every product's generated design;
    /// here they read Brasscribe's colour sets. Brasscribe's own roles are on its own type.
    @Test func neutralNamesReadTheProductsDesign() {
        func set(_ name: String) -> Color { Color("Brasscribe/" + name, bundle: ScribeDesign.bundle) }
        #expect(Color.Scribe.brand == set("brass"))
        #expect(Color.Scribe.brandText == set("brassText"))
        #expect(Color.Scribe.accent == set("brassText"))
        #expect(Color.Scribe.brandTint == set("brassTint"))
        #expect(Color.Scribe.line == set("staff"))
        #expect(Color.Scribe.ink == set("ink"))
        #expect(Color.Scribe.uncertain == set("uncertain"))
        #expect(Color.Brasscribe.veryUncertain == set("veryUncertain"))
        #expect(Color.Brasscribe.cursor == set("cursor"))
        #expect(ScribeDesign.Space.s4 == 16)
        #expect(ScribeDesign.Radius.md == 12)
        #expect(ScribeDesign.Size.touchMin == 44)
        #expect(BrasscribeDesign.Score.zoomMin < BrasscribeDesign.Score.zoomMax)
        #expect(Font.Scribe.title1 == Font.title.weight(.semibold))
    }

    @Test func markAndLicenceAreBundled() {
        #expect(Bundle.main.url(forResource: "mark", withExtension: "svg") != nil)
        #expect(Bundle.main.url(forResource: "OFL", withExtension: "txt") != nil)
    }
}
