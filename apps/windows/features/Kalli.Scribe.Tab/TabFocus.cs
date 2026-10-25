namespace Kalli.Scribe.Tab;

/// <summary>
/// The tab in full screen: the system bars, the top bar, the header and the player step aside and the tab has the
/// whole screen. A tap on the tab brings the controls back over it (<see cref="Controls"/>); while the recording plays
/// they step aside again by themselves. Leaving the mode brings everything back.
///
/// With a screen reader that is explored by touch the controls stay up: there is no tap on the tab to bring them back.
/// </summary>
public readonly record struct TabFocus(bool On = false, bool Controls = false)
{
    /// <summary>The controls hide by themselves this long after the last touch (<see cref="AutoHides"/>).</summary>
    public static readonly TimeSpan HideAfter = TimeSpan.FromSeconds(4);

    public TabFocus Enter() => new(On: true);

    public TabFocus Leave() => new();

    /// <summary>A tap on the tab shows the controls, and a second one hides them. Outside the mode it does nothing.</summary>
    public TabFocus Tapped() => On ? this with { Controls = !Controls } : this;

    /// <summary>The controls over the tab (the player, zoom and Leave full screen) are on screen.</summary>
    public bool ControlsShown(bool assistive) => On && (Controls || assistive);

    /// <summary>Only the small buttons are on screen: Play or Pause, and Leave full screen.</summary>
    public bool Minimal(bool assistive) => On && !ControlsShown(assistive);

    /// <summary>The controls hide by themselves <see cref="HideAfter"/> after the last touch, only while the recording plays.</summary>
    public bool AutoHides(bool playing, bool assistive) => On && Controls && playing && !assistive;
}
