import AppKit
import Testing
@testable import ScreenCatalogue

/// The rule for one screenshot, on readings and pictures given by hand. The apps' catalogues apply it to their screens.
@MainActor
struct TakeTests {
    /// A picture of 40 × 20 pixels in one grey, with `marks` drawn black on it (in pixels, origin top left).
    private func picture(_ grey: CGFloat = 1, marks: [CGRect] = []) -> NSBitmapImageRep {
        let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 40, pixelsHigh: 20, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                   isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        NSColor(deviceWhite: grey, alpha: 1).setFill()
        CGRect(x: 0, y: 0, width: 40, height: 20).fill()
        NSColor.black.setFill()
        for m in marks { CGRect(x: m.minX, y: 20 - m.maxY, width: m.width, height: m.height).fill() }
        NSGraphicsContext.restoreGraphicsState()
        return rep
    }

    /// A clock that goes a tenth of a second each time it is read.
    private final class Clock {
        var t: TimeInterval = 0
        func now() -> TimeInterval { t += 0.1; return t }
    }

    @Test func thePictureIsTheLastOfSoManyTheSameInARow() async throws {
        var taken = 0
        let rule = SteadyTake.Rule(takes: 3, bound: 30)
        let result = try await SteadyTake.take("screen", rule: rule, frames: {}, read: { Reading() }, picture: { taken += 1; return self.picture() })
        #expect(taken == 3)
        #expect(result.tries == 3)
        #expect(result.waited.isEmpty)
    }

    @Test func aConditionThatDoesNotHoldYetIsWaitedForAndNoPictureIsTakenMeanwhile() async throws {
        var reads = 0, taken = 0
        let result = try await SteadyTake.take("screen", rule: .init(takes: 2, bound: 30), frames: {}, read: {
            reads += 1
            return Reading(unmet: reads <= 3 ? "its score is not engraved yet" : nil)
        }, picture: { taken += 1; return self.picture() })
        #expect(taken == 2)
        #expect(result.waited.map(\.condition) == ["its score is not engraved yet"])
        #expect(result.waited.first?.tries == 3)
        #expect(result.line("score-light").contains("waited for: its score is not engraved yet (3)"))
    }

    @Test func aPictureCountsOnlyWhenTheReadingsBeforeAndAfterItAreTheSame() async throws {
        // The content arrives while the first picture is taken: the reading after it differs, so that take does not
        // count, and neither do the pictures before the change.
        var reads = 0
        let result = try await SteadyTake.take("screen", rule: .init(takes: 2, bound: 30), frames: {}, read: {
            reads += 1
            return Reading(state: reads == 1 ? "empty rows" : "rows")
        }, picture: { self.picture() })
        #expect(result.waited.map(\.condition) == [SteadyTake.moved])
        #expect(result.tries == 3)
    }

    @Test func aConditionThatStopsHoldingStartsTheCountAgain() async throws {
        var reads = 0, taken = 0
        // tries 1 and 2 hold (two reads each), try 3 does not, then it holds again
        let result = try await SteadyTake.take("screen", rule: .init(takes: 3, bound: 30), frames: {}, read: {
            reads += 1
            return Reading(unmet: reads == 5 ? "its content is drawn light" : nil)
        }, picture: { taken += 1; return self.picture() })
        #expect(taken == 5)
        #expect(result.tries == 6)
    }

    @Test func aPictureThatDoesNotShowWhatWasReadDoesNotCount() async throws {
        var taken = 0
        let result = try await SteadyTake.take("screen", rule: .init(takes: 2, bound: 30), frames: {}, read: { Reading() },
                                               picture: { taken += 1; return self.picture(marks: taken > 2 ? [CGRect(x: 4, y: 4, width: 6, height: 6)] : []) },
                                               drawn: { Pictures.isFlat($0, in: CGRect(x: 0, y: 0, width: 40, height: 20)) ? "nothing is drawn in its picture yet" : nil })
        #expect(taken == 4)
        #expect(result.waited.map(\.condition) == ["nothing is drawn in its picture yet"])
    }

    @Test func aScreenThatDoesNotKeepStillIsNotTaken() async {
        let clock = Clock()
        var taken = 0
        var last: NSBitmapImageRep?
        do {
            _ = try await SteadyTake.take("score-dark", rule: .init(takes: 3, bound: 5), now: clock.now, frames: {}, read: { Reading() },
                                          picture: { taken += 1; return self.picture(marks: [CGRect(x: taken % 30, y: 2, width: 4, height: 4)]) },
                                          lastPicture: { last = $0 })
            Issue.record("taken")
        } catch let notTaken as ScreenNotTaken {
            #expect(notTaken.waitedFor == SteadyTake.restless)
            #expect(notTaken.description.hasPrefix("screen not taken: score-dark: it does not keep still ("))
            #expect(last != nil)
        } catch {
            Issue.record("\(error)")
        }
    }

    @Test func aScreenThatNeverReachesItsConditionIsNotTakenAndNamesIt() async {
        let clock = Clock()
        var taken = 0
        do {
            _ = try await SteadyTake.take("review-contrast-dark", rule: .init(takes: 3, bound: 5), now: clock.now, frames: {},
                                          read: { Reading(unmet: "it is still loading (a spinner)") }, picture: { taken += 1; return self.picture() })
            Issue.record("taken")
        } catch let notTaken as ScreenNotTaken {
            #expect(notTaken.waitedFor == "it is still loading (a spinner)")
            #expect(taken == 0)
        } catch {
            Issue.record("\(error)")
        }
    }

    @Test func theAppearanceMustBeTheOneAskedForInTheWindowTheProcessAndTheContent() {
        let asked = Asked(dark: true, increasedContrast: true, language: "nb")
        let name = NSAppearance.Name.accessibilityHighContrastDarkAqua
        #expect(Conditions.appearance(asked, effective: name, systemContrast: true, seenDark: true, seenContrast: true, language: "nb") == nil)
        // the window is still as the screen before it left it
        #expect(Conditions.appearance(asked, effective: .darkAqua, systemContrast: true, seenDark: true, seenContrast: true, language: "nb") != nil)
        #expect(Conditions.appearance(asked, effective: name, systemContrast: false, seenDark: true, seenContrast: true, language: "nb")
            == "Increase Contrast is off for the process")
        // nothing of the screen has been drawn yet
        #expect(Conditions.appearance(asked, effective: name, systemContrast: true, seenDark: nil, seenContrast: nil, language: "nb")
            == "its content is not drawn yet")
        // the screen's own views are drawn in another appearance than the window's (a split view's column)
        #expect(Conditions.appearance(asked, effective: name, systemContrast: true, seenDark: true, seenContrast: false, language: "nb")
            == "its content is drawn with standard contrast")
        #expect(Conditions.appearance(asked, effective: name, systemContrast: true, seenDark: false, seenContrast: true, language: "nb")
            == "its content is drawn light")
        #expect(Conditions.appearance(asked, effective: name, systemContrast: true, seenDark: true, seenContrast: true, language: "en")
            == "the run is in en, not nb")
        #expect(Asked(dark: false, increasedContrast: true).appearance == .accessibilityHighContrastAqua)
        #expect(Asked(dark: false, increasedContrast: false).appearance == .aqua)
    }

    @Test func aSpinnerOrAnEmptyTreeIsContentNotThereYet() {
        let button = AXNode(role: "AXButton", label: "Done", frame: CGRect(x: 0, y: 0, width: 60, height: 28))
        let spinner = AXNode(role: "AXBusyIndicator", label: "", frame: CGRect(x: 10, y: 10, width: 16, height: 16))
        let words = AXNode(role: "AXStaticText", label: "", value: "4821", frame: CGRect(x: 0, y: 0, width: 60, height: 28))
        #expect(Conditions.content([button]) == nil)
        #expect(Conditions.content([]) != nil)
        #expect(Conditions.content([button, spinner]) == "it is still loading (a spinner)")
        #expect(Conditions.content([button, spinner], busyExpected: true) == nil)
        #expect(Conditions.content([words]) != nil)
        #expect(Conditions.content([words], controls: false) == nil)
    }

    @Test func aTextInTheTreeMustBeDrawnInThePicture() {
        // The picture is 40 × 20 pixels of a view of 20 × 10 points.
        let bounds = CGRect(x: 0, y: 0, width: 20, height: 10)
        let row = AXNode(role: "AXStaticText", label: "", value: "Bar 1, Solo Cornet", frame: CGRect(x: 2, y: 2, width: 8, height: 4))
        let mark = AXNode(role: "AXButton", label: "Play", frame: CGRect(x: 14, y: 2, width: 4, height: 4))
        // a list whose rows are not drawn yet: only the button is in the picture
        let early = picture(marks: [CGRect(x: 30, y: 6, width: 4, height: 4)])
        #expect(Conditions.drawn(early, nodes: [row, mark], bounds: bounds) == "its text “Bar 1, Solo Cornet” is not drawn in its picture yet")
        let done = picture(marks: [CGRect(x: 30, y: 6, width: 4, height: 4), CGRect(x: 6, y: 6, width: 10, height: 2)])
        #expect(Conditions.drawn(done, nodes: [row, mark], bounds: bounds) == nil)
        // a window that has drawn nothing
        #expect(Conditions.drawn(picture(), nodes: [mark], bounds: bounds) == "nothing is drawn in its picture yet")
        // a text scrolled out of its scroll area's view is not in the picture, and is not asked for
        let below = AXNode(role: "AXStaticText", label: "", value: "Bar 40", frame: CGRect(x: 2, y: 30, width: 8, height: 4),
                           viewport: CGRect(x: 0, y: 0, width: 20, height: 10))
        #expect(Conditions.drawn(done, nodes: [row, mark, below], bounds: bounds) == nil)
        // every text that is missing is named
        let second = AXNode(role: "AXStaticText", label: "", value: "Bar 2", frame: CGRect(x: 2, y: 6, width: 8, height: 4))
        #expect(Conditions.drawn(early, nodes: [row, second, mark], bounds: bounds) == "its texts “Bar 1, Solo Cornet”, “Bar 2” are not drawn in its picture yet")
    }

    @Test func onlyTheTextsListedAsUnreadableAreNotAskedFor() {
        let bounds = CGRect(x: 0, y: 0, width: 20, height: 10)
        let title = AXNode(role: "AXStaticText", label: "", value: "Speed", frame: CGRect(x: 2, y: 0, width: 8, height: 4))
        let row = AXNode(role: "AXStaticText", label: "", value: "Bar 1", frame: CGRect(x: 2, y: 5, width: 8, height: 4))
        let known = Unreadable(issue: "#1", screens: ["score-contrast": ["Speed"]])
        let neither = picture(marks: [CGRect(x: 30, y: 2, width: 4, height: 4)])
        // the listed text is not asked for; another text of the same screen still is
        #expect(Conditions.drawn(neither, nodes: [title, row], bounds: bounds, unreadable: known.covers("score-contrast")) == "its text “Bar 1” is not drawn in its picture yet")
        #expect(Conditions.drawn(neither, nodes: [title], bounds: bounds, unreadable: known.covers("score-contrast")) == nil)
        // and it is asked for on a screen it is not listed for
        #expect(Conditions.drawn(neither, nodes: [title], bounds: bounds, unreadable: known.covers("score-dark")) != nil)
        // a listed text that is drawn here is named for the log
        let both = picture(marks: [CGRect(x: 6, y: 3, width: 6, height: 2), CGRect(x: 6, y: 13, width: 6, height: 2), CGRect(x: 30, y: 2, width: 4, height: 4)])
        #expect(known.drawnAfterAll("score-contrast", picture: both, nodes: [title, row], bounds: bounds)?.contains("“Speed”") == true)
        #expect(known.drawnAfterAll("score-contrast", picture: neither, nodes: [title, row], bounds: bounds) == nil)
    }

    @Test func anAreaOfOneColourIsFlat() {
        let rep = picture(0.5, marks: [CGRect(x: 20, y: 10, width: 2, height: 2)])
        #expect(Pictures.isFlat(rep, in: CGRect(x: 0, y: 0, width: 18, height: 20)))
        #expect(!Pictures.isFlat(rep, in: CGRect(x: 0, y: 0, width: 40, height: 20)))
        #expect(Pictures.pixels(rep) == Pictures.pixels(picture(0.5, marks: [CGRect(x: 20, y: 10, width: 2, height: 2)])))
        #expect(Pictures.pixels(rep) != Pictures.pixels(picture(0.5)))
    }
}
