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
        #expect(UIColor(named: "Brasscribe/\(name)", in: BrasscribeDesign.bundle, compatibleWith: nil) != nil)
        #else
        #expect(NSColor(named: "Brasscribe/\(name)", bundle: BrasscribeDesign.bundle) != nil)
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
    /// here they read Brasscribe's.
    @Test func neutralNamesReadTheProductsDesign() {
        #expect(Color.Scribe.brand == Color.Brasscribe.brass)
        #expect(Color.Scribe.brandText == Color.Brasscribe.brassText)
        #expect(Color.Scribe.brandTint == Color.Brasscribe.brassTint)
        #expect(Color.Scribe.line == Color.Brasscribe.staff)
        #expect(Color.Scribe.ink == Color.Brasscribe.ink)
        #expect(Color.Scribe.uncertain == Color.Brasscribe.uncertain)
        #expect(ScribeDesign.Space.s4 == BrasscribeDesign.Space.s4)
        #expect(ScribeDesign.Radius.md == BrasscribeDesign.Radius.md)
        #expect(ScribeDesign.Size.touchMin == BrasscribeDesign.Size.touchMin)
        #expect(ScribeDesign.Motion.base == BrasscribeDesign.Motion.base)
        #expect(ScribeDesign.bundle == BrasscribeDesign.bundle)
        #expect(Font.Scribe.title1 == Font.Brasscribe.title1)
    }

    @Test func markAndLicenceAreBundled() {
        #expect(Bundle.main.url(forResource: "mark", withExtension: "svg") != nil)
        #expect(Bundle.main.url(forResource: "OFL", withExtension: "txt") != nil)
    }
}
