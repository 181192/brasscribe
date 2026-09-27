using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;

namespace Brasscribe.Play.Views;

/// <summary>
/// <see cref="Screens"/> as Visibility, for x:Bind function bindings on Visibility. A function that
/// returns bool bound to Visibility makes the XAML compiler emit a bool-to-Visibility cast that does
/// not compile (CS0103 "obj", microsoft/microsoft-ui-xaml#8644), so these return Visibility.
/// </summary>
public static class Shown
{
    private static Visibility Of(bool visible) => visible ? Visibility.Visible : Visibility.Collapsed;

    public static Visibility IsScore(Screen current) => Of(Screens.IsScore(current));
    public static Visibility Not(bool value) => Of(Screens.Not(value));
    public static Visibility HasText(string? value) => Of(Screens.HasText(value));
    public static Visibility HasNotes(int count) => Of(Screens.HasNotes(count));
    public static Visibility Both(bool a, bool b) => Of(Screens.Both(a, b));
    public static Visibility UncertainOpen(bool kept, bool veryUncertain) => Of(Screens.UncertainOpen(kept, veryUncertain));
    public static Visibility VeryUncertainOpen(bool kept, bool veryUncertain) => Of(Screens.VeryUncertainOpen(kept, veryUncertain));

    /// <summary>A choice that can't be made is shown dimmed (it stays focusable, with its reason as text).</summary>
    public static double Dimmed(bool available) => available ? 1.0 : 0.55;
}
