import Testing
@testable import TabKit

/// Full screen for the tab: what shows when, without a screen.
struct TabFocusTests {
    @Test func startsOutsideTheModeWithNothingToHide() {
        let focus = TabFocus()
        #expect(!focus.on)
        #expect(!focus.controlsShown(assistive: false))
        #expect(!focus.minimal(assistive: false))
    }

    @Test func enteringHidesTheControlsLeavingBringsEverythingBack() {
        let inside = TabFocus().enter()
        #expect(inside.on)
        #expect(inside.minimal(assistive: false))
        #expect(!inside.controlsShown(assistive: false))
        #expect(inside.tapped().leave() == TabFocus())
    }

    @Test func aTapShowsTheControlsAndASecondOneHidesThem() {
        let shown = TabFocus().enter().tapped()
        #expect(shown.controlsShown(assistive: false))
        #expect(!shown.minimal(assistive: false))
        #expect(!shown.tapped().controlsShown(assistive: false))
    }

    @Test func aTapOutsideTheModeDoesNothing() {
        #expect(TabFocus().tapped() == TabFocus())
    }

    @Test func theControlsHideByThemselvesOnlyWhilePlayingAndWithoutAScreenReader() {
        let shown = TabFocus().enter().tapped()
        #expect(shown.autoHides(playing: true, assistive: false))
        #expect(!shown.autoHides(playing: false, assistive: false))
        #expect(!shown.autoHides(playing: true, assistive: true))
        #expect(!TabFocus().enter().autoHides(playing: true, assistive: false))
        #expect(!TabFocus().autoHides(playing: true, assistive: false))
    }

    @Test func withAScreenReaderTheControlsStayUp() {
        let inside = TabFocus().enter()
        #expect(inside.controlsShown(assistive: true))
        #expect(!inside.minimal(assistive: true))
    }
}
