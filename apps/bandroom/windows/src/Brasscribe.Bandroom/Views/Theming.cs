using Brasscribe.Bandroom.Core.Appearance;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;

namespace Brasscribe.Bandroom.Views;

/// <summary>
/// Appearance (design/system.md §10) on every open window: RequestedTheme on the window's root (never
/// Application.RequestedTheme, which can't change after start) and the caption buttons of the title bar.
/// Menus and other popups follow the root they open from. Default follows Windows and every contrast theme.
/// </summary>
internal sealed class ThemedWindows(ResolvedTheme initial)
{
    private readonly List<(Window Window, FrameworkElement Root)> _open = [];

    public ElementTheme Theme { get; private set; } = ToElement(initial);

    /// <summary>Themes the window now and whenever the choice changes, until it closes.</summary>
    public void Track(Window window, FrameworkElement root)
    {
        _open.Add((window, root));
        Apply(window, root);
        window.Closed += (_, _) => _open.RemoveAll(w => ReferenceEquals(w.Window, window));
    }

    public void Set(ResolvedTheme theme)
    {
        Theme = ToElement(theme);
        foreach (var (window, root) in _open.ToList()) Apply(window, root);
    }

    private void Apply(Window window, FrameworkElement root)
    {
        root.RequestedTheme = Theme;
        window.AppWindow.TitleBar.PreferredTheme = Theme switch
        {
            ElementTheme.Light => TitleBarTheme.Light,
            ElementTheme.Dark => TitleBarTheme.Dark,
            _ => TitleBarTheme.UseDefaultAppMode,
        };
    }

    private static ElementTheme ToElement(ResolvedTheme theme) => theme switch
    {
        ResolvedTheme.Light => ElementTheme.Light,
        ResolvedTheme.Dark => ElementTheme.Dark,
        _ => ElementTheme.Default,
    };
}

/// <summary>
/// Theme brushes for code-behind. Application.Current.Resources answers for the app's theme only, so a
/// window forced to Light or Dark looks its brushes up in the matching theme dictionary itself.
/// </summary>
internal static class ThemeBrushes
{
    private static readonly Windows.UI.ViewManagement.AccessibilitySettings Accessibility = new();

    /// <summary>The brush for <paramref name="key"/> as the element shows it now.</summary>
    public static Brush For(FrameworkElement element, string key)
    {
        string dictionary = Accessibility.HighContrast ? "HighContrast"
            : element.ActualTheme == ElementTheme.Dark ? "Dark" : "Light";
        return Find(Application.Current.Resources, dictionary, key) as Brush
            ?? (Application.Current.Resources.TryGetValue(key, out var v) && v is Brush b ? b : new SolidColorBrush(Colors.Gray));
    }

    private static object? Find(ResourceDictionary rd, string dictionary, string key)
    {
        // As in XAML lookup: the dictionary's own entries first, then later merged dictionaries before earlier ones.
        if (rd.ThemeDictionaries.TryGetValue(dictionary, out var d) && d is ResourceDictionary theme
            && theme.TryGetValue(key, out var value)) return value;
        for (int i = rd.MergedDictionaries.Count - 1; i >= 0; i--)
            if (Find(rd.MergedDictionaries[i], dictionary, key) is { } found) return found;
        return null;
    }
}
