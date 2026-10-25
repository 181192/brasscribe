/// The tab in full screen: the system bars, the top bar, the header and the player step aside and the tab has the whole
/// screen. A tap on the tab brings the controls back over it (`controls`); while the recording plays they step aside again
/// by themselves. Leaving the mode brings everything back.
///
/// With a screen reader that is explored by touch the controls stay up: there is no tap on the tab to bring them back.
public struct TabFocus: Equatable, Sendable {
    public var on: Bool
    public var controls: Bool

    public init(on: Bool = false, controls: Bool = false) {
        self.on = on
        self.controls = controls
    }

    /// The controls hide by themselves this long after the last touch, only while the recording plays.
    public static let hideAfter: Duration = .seconds(4)

    public func enter() -> TabFocus { TabFocus(on: true) }

    public func leave() -> TabFocus { TabFocus() }

    /// A tap on the tab shows the controls, and a second one hides them. Outside the mode it does nothing.
    public func tapped() -> TabFocus { on ? TabFocus(on: on, controls: !controls) : self }

    /// The controls over the tab (the player, zoom and Leave full screen) are on screen.
    public func controlsShown(assistive: Bool) -> Bool { on && (controls || assistive) }

    /// Only the small buttons are on screen: Play or Pause, and Leave full screen.
    public func minimal(assistive: Bool) -> Bool { on && !controlsShown(assistive: assistive) }

    /// The controls hide by themselves `hideAfter` the last touch, only while the recording plays.
    public func autoHides(playing: Bool, assistive: Bool) -> Bool { on && controls && playing && !assistive }
}
