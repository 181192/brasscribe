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

    /// <summary>
    /// In Light and Dark the brush is built from the theme's colour (BcLoopTintBrush from BcLoopTintColor). A theme
    /// dictionary's brush that no XAML has used yet can resolve its {StaticResource ...Color} in the app's theme instead
    /// of its own, so Dark handed back Light's loop and selection tints. The colours are plain values in each theme.
    /// </summary>
    public static Brush Brush(FrameworkElement element, string key)
    {
        string theme = ThemeKey(element);
        if (theme != "HighContrast" && key.EndsWith("Brush", StringComparison.Ordinal))
        {
            string colorKey = key[..^"Brush".Length] + "Color";
            if ((Find(element.Resources, colorKey, theme) ?? Find(Application.Current.Resources, colorKey, theme)) is Windows.UI.Color color)
                return new SolidColorBrush(color);
        }
        return Find(element.Resources, key, theme) as Brush
            ?? Find(Application.Current.Resources, key, theme) as Brush
            ?? new SolidColorBrush(Colors.Black);
    }

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
