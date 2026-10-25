using Kalli.Scribe.Tab;
using Kalli.Scribe.ViewModels;
using Microsoft.UI.Xaml;

namespace Kalli.Fretscribe.Views;

/// <summary>
/// Small functions as Visibility, for x:Bind function bindings on Visibility. A function that returns bool bound to
/// Visibility makes the XAML compiler emit a bool-to-Visibility cast that does not compile
/// (CS0103 "obj", microsoft/microsoft-ui-xaml#8644), so these return Visibility.
/// </summary>
public static class Shown
{
    private static Visibility Of(bool visible) => visible ? Visibility.Visible : Visibility.Collapsed;

    /// <summary>Your songs shows in the pane on Home and while a tab is written.</summary>
    public static bool Library(TabScreen current) => current is TabScreen.Home or TabScreen.Transcribing;

    public static Visibility Not(bool value) => Of(!value);
    public static Visibility HasText(string? value) => Of(!string.IsNullOrEmpty(value));
    public static Visibility If(bool value) => Of(value);
    public static Visibility IfNull(object? value) => Of(value is null);
    public static Visibility NotNull(object? value) => Of(value is not null);
    public static Visibility Both(bool a, bool b) => Of(a && b);
    public static Visibility AndNot(bool a, bool b) => Of(a && !b);
    public static Visibility Neither(bool a, bool b) => Of(!a && !b);
    public static bool Is(bool value) => value;
    public static double Opaque(bool shown) => shown ? 1 : 0;
}
