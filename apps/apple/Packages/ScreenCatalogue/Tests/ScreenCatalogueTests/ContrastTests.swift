import AppKit
import Testing
@testable import ScreenCatalogue

/// "Drawn" means readable: the contrast a text has with its ground, measured in pictures made by hand.
@MainActor
struct ContrastTests {
    /// A grey of the sRGB value `white` (0–255), or see-through.
    private func grey(_ white: Int, alpha: CGFloat = 1) -> NSColor { NSColor(deviceWhite: CGFloat(white) / 255, alpha: alpha) }

    /// A picture of 40 × 20 pixels of a view of 20 × 10 points: `ground` (nil: nothing drawn, see-through) with `marks`
    /// drawn on it, each in its colour (in pixels, origin top left).
    private func picture(ground: NSColor?, marks: [(CGRect, NSColor)] = []) -> NSBitmapImageRep {
        let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 40, pixelsHigh: 20, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                   isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        if let ground {
            ground.setFill()
            CGRect(x: 0, y: 0, width: 40, height: 20).fill()
        }
        for (m, colour) in marks {
            colour.setFill()
            CGRect(x: m.minX, y: 20 - m.maxY, width: m.width, height: m.height).fill()
        }
        NSGraphicsContext.restoreGraphicsState()
        return rep
    }

    private let view = CGRect(x: 0, y: 0, width: 20, height: 10)
    /// A text in the upper left: 2,2 8 × 4 pt, which is 4,4 16 × 8 in pixels.
    private let frame = CGRect(x: 4, y: 4, width: 16, height: 8)
    private func text(_ words: String, y: CGFloat = 2) -> AXNode {
        AXNode(role: "AXStaticText", label: "", value: words, frame: CGRect(x: 2, y: y, width: 8, height: 4))
    }
    /// The glyphs of the text in the upper left (or, with `y` 12, the one below it).
    private func glyphs(_ colour: NSColor, y: CGFloat = 6) -> (CGRect, NSColor) { (CGRect(x: 6, y: y, width: 10, height: 2), colour) }
    /// Something else on the screen, so that a picture is not one flat colour.
    private var other: (CGRect, NSColor) { (CGRect(x: 30, y: 14, width: 4, height: 4), .black) }

    @Test func theRatioIsTheOneWCAGGivesTheTwoColours() throws {
        // Known pairs: black on white is 21:1; #767676 on white just passes 4.5:1, #777777 just fails; #595959 on white is 7:1.
        #expect(abs(try #require(Pictures.contrast(picture(ground: .white, marks: [glyphs(.black)]), in: frame)) - 21) < 0.01)
        #expect(abs(try #require(Pictures.contrast(picture(ground: .white, marks: [glyphs(grey(0x76))]), in: frame)) - 4.54) < 0.01)
        #expect(abs(try #require(Pictures.contrast(picture(ground: .white, marks: [glyphs(grey(0x77))]), in: frame)) - 4.48) < 0.01)
        #expect(abs(try #require(Pictures.contrast(picture(ground: .white, marks: [glyphs(grey(0x59))]), in: frame)) - 7.0) < 0.01)
        // light on dark is the same ratio the other way round
        #expect(abs(try #require(Pictures.contrast(picture(ground: .black, marks: [glyphs(.white)]), in: frame)) - 21) < 0.01)
        // nothing drawn there
        #expect(Pictures.contrast(picture(ground: .white, marks: [other]), in: frame) == 1)
    }

    @Test func theGroundIsWhatMostOfTheFrameIsAndTheTextIsItsFurthestColour() throws {
        // Glyph edges blend into the ground: the core of the glyphs counts, not their mean.
        let edges = (CGRect(x: 6, y: 5, width: 10, height: 4), grey(0xB0))
        let rep = picture(ground: .white, marks: [edges, glyphs(grey(0x59))])
        #expect(abs(try #require(Pictures.contrast(rep, in: frame)) - 7.0) < 0.01)
        // A ground with dithering a few steps wide is one ground.
        let dithered = picture(ground: .white, marks: [(CGRect(x: 4, y: 4, width: 16, height: 3), grey(0xFD)), glyphs(grey(0x59), y: 9)])
        #expect(abs(try #require(Pictures.contrast(dithered, in: frame)) - 7.0) < 0.1)
    }

    @Test func oneStrayPixelIsNotTheText() throws {
        // A black pixel of a neighbour's edge inside the frame of a grey text: the text is still as faint as it is.
        let stray = (CGRect(x: 19, y: 4, width: 1, height: 2), NSColor.black)
        let rep = picture(ground: .white, marks: [glyphs(grey(0x99)), stray])
        #expect(try #require(Pictures.contrast(rep, in: frame)) < 3)
        // three pixels and more are something drawn
        let more = (CGRect(x: 18, y: 4, width: 2, height: 2), NSColor.black)
        #expect(try #require(Pictures.contrast(picture(ground: .white, marks: [glyphs(grey(0x99)), more]), in: frame)) > 20)
    }

    @Test func aTextWithoutAGroundInThePictureHasNoRatio() {
        // The view draws its text and nothing behind it: what is behind the view on a Mac decides, and the picture cannot say.
        let rep = picture(ground: nil, marks: [glyphs(.black), other])
        #expect(Pictures.contrast(rep, in: frame) == nil)
        #expect(Conditions.readable(rep, nodes: [text("Play when you're ready.")], bounds: view, minimum: 4.5)
            == "its text “Play when you're ready.” has no ground drawn behind it, so nothing gives it 4.5:1")
    }

    @Test func aTextMustHaveTheContrastItsVariantAsksFor() {
        #expect(Conditions.minimumContrast(increased: false) == 4.5)
        #expect(Conditions.minimumContrast(increased: true) == 7)
        // #6A6A6A on white is 5.41:1: readable, and not enough under Increase Contrast.
        let rep = picture(ground: .white, marks: [glyphs(grey(0x6A)), other])
        let caption = text("Very unsure")
        #expect(Conditions.readable(rep, nodes: [caption], bounds: view, minimum: 4.5) == nil)
        #expect(Conditions.readable(rep, nodes: [caption], bounds: view, minimum: 7) == "its text “Very unsure” is 5.41:1 on its ground, under 7:1")
        // Near invisible: something is drawn, which used to be enough.
        let faint = picture(ground: .white, marks: [glyphs(grey(0xE0)), other])
        #expect(!Pictures.isFlat(faint, in: frame))
        #expect(Conditions.readable(faint, nodes: [caption], bounds: view, minimum: 4.5) == "its text “Very unsure” is 1.32:1 on its ground, under 4.5:1")
        // A text that passes exactly passes.
        #expect(Conditions.readable(picture(ground: .white, marks: [glyphs(grey(0x59)), other]), nodes: [caption], bounds: view, minimum: 7) == nil)
    }

    @Test func everyFaintTextIsNamedWithItsRatio() {
        let rep = picture(ground: .white, marks: [glyphs(grey(0x6A)), glyphs(grey(0x99), y: 12), other])
        let nodes = [text("Brasscribe wasn't sure"), text("Very unsure", y: 5)]
        #expect(Conditions.readable(rep, nodes: nodes, bounds: view, minimum: 7)
            == "its texts “Brasscribe wasn't sure” (5.41:1), “Very unsure” (2.85:1) are under 7:1 on their ground")
        #expect(Conditions.faint(rep, nodes: nodes, bounds: view, minimum: 4.5).map(\.node.words) == ["Very unsure"])
        // A text that is not drawn yet is not a faint one: it is waited for, by the words it always had.
        let early = picture(ground: .white, marks: [glyphs(.black, y: 12), other])
        #expect(Conditions.drawn(early, nodes: nodes, bounds: view) == "its text “Brasscribe wasn't sure” is not drawn in its picture yet")
        #expect(Conditions.readable(early, nodes: nodes, bounds: view, minimum: 7) == nil)
        // and a faint one is drawn: nothing to wait for
        #expect(Conditions.drawn(rep, nodes: nodes, bounds: view) == nil)
    }

    @Test func aFaintTextInASteadyPictureFailsTheTakeAtOnce() async {
        // The screen keeps still and is the one asked for; its caption is too faint. Waiting would not change it:
        // the take ends as soon as it has its steady pictures, with the text and its ratio.
        let caption = text("Very unsure")
        let rep = picture(ground: .white, marks: [glyphs(grey(0x6A)), other])
        var taken = 0
        var clock = 0.0
        do {
            _ = try await SteadyTake.take("review-contrast", rule: .init(takes: 3, bound: 30), now: { clock += 0.1; return clock }, frames: {},
                                          read: { Reading() }, picture: { taken += 1; return rep },
                                          drawn: { Conditions.drawn($0, nodes: [caption], bounds: self.view) },
                                          readable: { Conditions.readable($0, nodes: [caption], bounds: self.view, minimum: 7) })
            Issue.record("taken")
        } catch let notTaken as ScreenNotTaken {
            #expect(taken == 3)
            #expect(notTaken.unreadable)
            #expect(notTaken.seconds < 1)
            #expect(notTaken.description.hasPrefix("screen not taken: review-contrast: its text “Very unsure” is 5.41:1 on its ground, under 7:1 ("))
        } catch {
            Issue.record("\(error)")
        }
    }

    @Test func aTextNotDrawnYetIsStillWaitedForAndCountsAsNotTaken() async {
        // The caption's frame is empty the whole time: that is waited for to the bound, and is not "unreadable".
        let caption = text("Very unsure")
        let rep = picture(ground: .white, marks: [other])
        var clock = 0.0
        do {
            _ = try await SteadyTake.take("review-contrast", rule: .init(takes: 3, bound: 5), now: { clock += 0.1; return clock }, frames: {},
                                          read: { Reading() }, picture: { rep },
                                          drawn: { Conditions.drawn($0, nodes: [caption], bounds: self.view) },
                                          readable: { Conditions.readable($0, nodes: [caption], bounds: self.view, minimum: 7) })
            Issue.record("taken")
        } catch let notTaken as ScreenNotTaken {
            #expect(!notTaken.unreadable)
            #expect(notTaken.seconds >= 5)
            #expect(notTaken.waitedFor == "its text “Very unsure” is not drawn in its picture yet")
        } catch {
            Issue.record("\(error)")
        }
    }

    @Test func aReadableSteadyPictureIsTaken() async throws {
        let caption = text("Very unsure")
        let rep = picture(ground: .white, marks: [glyphs(.black), other])
        let result = try await SteadyTake.take("review-contrast", rule: .init(takes: 3, bound: 30), frames: {}, read: { Reading() }, picture: { rep },
                                               readable: { Conditions.readable($0, nodes: [caption], bounds: self.view, minimum: 7) })
        #expect(result.tries == 3)
    }

    @Test func aFaintTextCanBeListedAsUnreadableAndTheEntryGoesStaleWhenItCanBeRead() {
        let nodes = [text("Brasscribe wasn't sure"), text("Very unsure", y: 5)]
        let known = Unreadable(issue: "#1", screens: ["review-contrast": ["Very unsure"]])
        let rep = picture(ground: .white, marks: [glyphs(.black), glyphs(grey(0x99), y: 12), other])
        #expect(Conditions.readable(rep, nodes: nodes, bounds: view, minimum: 7, unreadable: known.covers("review-contrast", in: nodes)) == nil)
        #expect(known.stale("review-contrast", picture: rep, nodes: nodes, bounds: view, minimum: 7) == nil)
        // only the listed one is excused
        let both = picture(ground: .white, marks: [glyphs(grey(0x6A)), glyphs(grey(0x99), y: 12), other])
        #expect(Conditions.readable(both, nodes: nodes, bounds: view, minimum: 7, unreadable: known.covers("review-contrast", in: nodes))
            == "its text “Brasscribe wasn't sure” is 5.41:1 on its ground, under 7:1")
        // fixed: the entry has to go
        let fixed = picture(ground: .white, marks: [glyphs(.black), glyphs(.black, y: 12), other])
        #expect(known.stale("review-contrast", picture: fixed, nodes: nodes, bounds: view, minimum: 7)
            == "review-contrast: listed as unreadable (#1), but readable or not on the screen: “Very unsure”. Take it out of the list.")
        // 2.85:1 is short of either bar; 5.41:1 only of the higher one
        let partly = Unreadable(issue: "#1", screens: ["review": ["Brasscribe wasn't sure"]])
        #expect(partly.stale("review", picture: both, nodes: nodes, bounds: view, minimum: 4.5) != nil)
        #expect(partly.stale("review", picture: both, nodes: nodes, bounds: view, minimum: 7) == nil)
    }

    @Test func aRatioIsWrittenAsItIsRead() {
        #expect(Conditions.ratio(7) == "7:1")
        #expect(Conditions.ratio(4.5) == "4.5:1")
        #expect(Conditions.ratio(4.654) == "4.65:1")
        #expect(Conditions.ratio(6.199) == "6.2:1")
        #expect(Conditions.ratio(21) == "21:1")
        #expect(Conditions.ratio(1.05) == "1.05:1")
    }
}
