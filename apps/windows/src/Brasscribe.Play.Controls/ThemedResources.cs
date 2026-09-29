using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;

namespace Brasscribe.Play.Controls;

/// <summary>
/// Theme resources looked up from code for an element's own theme. Application.Current.Resources[key] resolves
/// theme dictionaries for the app's theme (the system's), so with Appearance set to Light or Dark on the window
/// root (design/system.md §10) it would hand back the other theme's brush. A contrast theme always wins.
/// </summary>
public static class ThemedResources
{
    private static readonly Windows.UI.ViewManagement.AccessibilitySettings Accessibility = new();

    /// <summary>The key of the theme dictionary that applies to this element now.</summary>
    public static string ThemeKey(FrameworkElement element) =>
        Accessibility.HighContrast ? "HighContrast" : element.ActualTheme == ElementTheme.Dark ? "Dark" : "Light";

    public static Brush Brush(FrameworkElement element, string key) =>
        Find(element.Resources, key, ThemeKey(element)) as Brush
        ?? Find(Application.Current.Resources, key, ThemeKey(element)) as Brush
        ?? new SolidColorBrush(Colors.Black);

    private static object? Find(ResourceDictionary dictionary, string key, string theme)
    {
        if (dictionary.ThemeDictionaries.TryGetValue(theme, out var t) && t is ResourceDictionary themed
            && themed.TryGetValue(key, out var hit))
            return hit;
        // Merged dictionaries: the last one wins, as in XAML.
        for (int i = dictionary.MergedDictionaries.Count - 1; i >= 0; i--)
            if (Find(dictionary.MergedDictionaries[i], key, theme) is { } found) return found;
        return dictionary.TryGetValue(key, out var plain) ? plain : null;
    }
}
