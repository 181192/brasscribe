using Brasscribe.ScreenCheck;

namespace Brasscribe.ScreenCheck.Tests;

/// <summary>Which part of the window the walk with Tab must reach everything in.</summary>
public class KeyboardScopeTests
{
    private static readonly ScopeNode Window = new("w", false), Content = new("c", false), Pane = new("p", false),
        Dialog = new("d", true), Elsewhere = new("e", false);

    [Fact]
    public void Tab_caught_in_one_pane_still_checks_the_whole_window() =>
        Assert.Null(KeyboardScope.Choose([[Window, Content, Pane], [Window, Content, Pane]]));

    [Fact]
    public void An_open_dialog_that_holds_every_stop_is_the_scope() =>
        Assert.Equal(Dialog, KeyboardScope.Choose([[Window, Dialog], [Window, Dialog, Pane]]));

    [Fact]
    public void A_dialog_the_focus_left_is_not_the_scope() =>
        Assert.Null(KeyboardScope.Choose([[Window, Dialog], [Window, Content, Elsewhere]]));

    [Fact]
    public void No_stops_checks_the_whole_window() => Assert.Null(KeyboardScope.Choose([]));
}
