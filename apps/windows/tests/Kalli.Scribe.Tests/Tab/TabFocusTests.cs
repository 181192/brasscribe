using Kalli.Scribe.Tab;

namespace Kalli.Scribe.Tests;

/// <summary>Full screen for the tab: what shows when, without a screen.</summary>
public class TabFocusTests
{
    [Fact]
    public void Starts_outside_the_mode_with_nothing_to_hide()
    {
        var focus = new TabFocus();
        Assert.False(focus.On);
        Assert.False(focus.ControlsShown(assistive: false));
        Assert.False(focus.Minimal(assistive: false));
    }

    [Fact]
    public void Entering_hides_the_controls_leaving_brings_everything_back()
    {
        var inside = new TabFocus().Enter();
        Assert.True(inside.On);
        Assert.True(inside.Minimal(assistive: false));
        Assert.False(inside.ControlsShown(assistive: false));
        Assert.Equal(new TabFocus(), inside.Tapped().Leave());
    }

    [Fact]
    public void A_tap_shows_the_controls_and_a_second_one_hides_them()
    {
        var shown = new TabFocus().Enter().Tapped();
        Assert.True(shown.ControlsShown(assistive: false));
        Assert.False(shown.Minimal(assistive: false));
        Assert.False(shown.Tapped().ControlsShown(assistive: false));
    }

    [Fact]
    public void A_tap_outside_the_mode_does_nothing() => Assert.Equal(new TabFocus(), new TabFocus().Tapped());

    [Fact]
    public void The_controls_hide_by_themselves_only_while_playing_and_without_a_screen_reader()
    {
        var shown = new TabFocus().Enter().Tapped();
        Assert.True(shown.AutoHides(playing: true, assistive: false));
        Assert.False(shown.AutoHides(playing: false, assistive: false));
        Assert.False(shown.AutoHides(playing: true, assistive: true));
        Assert.False(new TabFocus().Enter().AutoHides(playing: true, assistive: false));
        Assert.False(new TabFocus().AutoHides(playing: true, assistive: false));
        Assert.Equal(TimeSpan.FromSeconds(4), TabFocus.HideAfter);
    }

    [Fact]
    public void With_a_screen_reader_the_controls_stay_up()
    {
        var inside = new TabFocus().Enter();
        Assert.True(inside.ControlsShown(assistive: true));
        Assert.False(inside.Minimal(assistive: true));
    }
}
