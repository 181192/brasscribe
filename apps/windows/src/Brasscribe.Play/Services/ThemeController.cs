using System.ComponentModel;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.UI.ViewManagement;

namespace Brasscribe.Play.Services;

/// <summary>
/// Settings › Display › Appearance (design/system.md §10). The theme is set on each window's root element
/// (Application.RequestedTheme cannot change after start-up), on open dialogs and flyouts (they live in the
/// popup layer and don't inherit it), and on the caption buttons. A Windows contrast theme always wins:
/// the roots then ask for Default and the choice is kept for later.
/// Pink is a palette, not a theme: its generated dictionary (Light and Dark roles) is merged after the
/// Brasscribe theme while it is chosen, and the roots flip their theme once so every ThemeResource looks again.
/// </summary>
public sealed class ThemeController
{
    private readonly SettingsViewModel _settings;
    private readonly DispatcherQueue _queue;
    private readonly AccessibilitySettings _accessibility = new();
    private readonly List<Window> _windows = [];
    private readonly RootTheme? _override;
    private const string PinkSource = "ms-appx:///Themes/BrasscribePinkTheme.xaml";
    private ResourceDictionary? _pink;

    /// <param name="forced">"--theme light|dark" for screenshots: wins over the stored choice (not over contrast).</param>
    public ThemeController(SettingsViewModel settings, DispatcherQueue queue, string? forced)
    {
        _settings = settings;
        _queue = queue;
        _override = forced switch { "dark" => RootTheme.Dark, "light" => RootTheme.Light, _ => null };
        _settings.HighContrast = _accessibility.HighContrast;
        // Raised off the UI thread.
        _accessibility.HighContrastChanged += (s, _) => _queue.TryEnqueue(() => _settings.HighContrast = s.HighContrast);
        _settings.PropertyChanged += OnSettingsChanged;
        ApplyPalette();
    }

    /// <summary>The theme roots and popups ask for now.</summary>
    public ElementTheme Current => (ElementTheme)(_settings.HighContrast ? RootTheme.Default : _override ?? _settings.RootTheme);

    /// <summary>The theme for a new ContentDialog shown in this app.</summary>
    public static ElementTheme ForDialogs => (Application.Current as App)?.Theme?.Current ?? ElementTheme.Default;

    /// <summary>Themes a window now and whenever the choice or the contrast theme changes.</summary>
    public void Attach(Window window)
    {
        _windows.Add(window);
        window.Closed += (_, _) => _windows.Remove(window);
        if (window.Content is FrameworkElement root)
            root.ActualThemeChanged += (_, _) => ApplyCaptionButtons(window);
        Apply(window);
    }

    private void OnSettingsChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is not (nameof(SettingsViewModel.RootTheme) or nameof(SettingsViewModel.UsesPink))) return;
        bool repaint = ApplyPalette();
        foreach (var w in _windows.ToList()) Apply(w, repaint);
    }

    /// <summary>Merges the Pink palette in while it is in use, and out otherwise; true when that changed.</summary>
    private bool ApplyPalette()
    {
        var merged = Application.Current.Resources.MergedDictionaries;
        bool want = _settings.UsesPink;
        bool has = _pink is not null && merged.Contains(_pink);
        if (want == has) return false;
        if (want)
        {
            _pink ??= new ResourceDictionary { Source = new Uri(PinkSource) };
            merged.Add(_pink); // last, so its colour roles win over BrasscribeTheme.xaml's
        }
        else merged.Remove(_pink!);
        return true;
    }

    private void Apply(Window window, bool repaint = false)
    {
        var theme = Current;
        if (window.Content is FrameworkElement root)
        {
            Theme(root, theme, repaint);
            // Open dialogs (Settings itself) and flyouts re-theme at once, with focus left where it was.
            if (root.XamlRoot is { } xamlRoot)
                foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(xamlRoot))
                    if (popup.Child is FrameworkElement child) Theme(child, theme, repaint);
        }
        ApplyCaptionButtons(window);
    }

    /// <summary>
    /// ThemeResource references look again only when an element's theme changes: after the palette changed, the
    /// element flips to the other theme once and back, so the new palette's brushes are picked up.
    /// </summary>
    private static void Theme(FrameworkElement element, ElementTheme theme, bool repaint)
    {
        if (repaint) element.RequestedTheme = element.ActualTheme == ElementTheme.Dark ? ElementTheme.Light : ElementTheme.Dark;
        element.RequestedTheme = theme;
    }

    /// <summary>A colour of the Pink palette for the root's light or dark, while Pink is in use.</summary>
    private Windows.UI.Color? PinkColor(string key, bool dark) =>
        _settings.UsesPink && _pink?.ThemeDictionaries.TryGetValue(dark ? "Dark" : "Light", out var d) == true
        && d is ResourceDictionary themed && themed.TryGetValue(key, out var v) && v is Windows.UI.Color c ? c : null;

    /// <summary>The minimise/maximise/close glyphs follow the root's theme; a contrast theme keeps the system's.</summary>
    private void ApplyCaptionButtons(Window window)
    {
        var bar = window.AppWindow.TitleBar;
        if (_settings.HighContrast || window.Content is not FrameworkElement root)
        {
            bar.ButtonForegroundColor = null;
            bar.ButtonHoverForegroundColor = null;
            bar.ButtonHoverBackgroundColor = null;
            bar.ButtonPressedForegroundColor = null;
            bar.ButtonPressedBackgroundColor = null;
            bar.ButtonInactiveForegroundColor = null;
            bar.ButtonBackgroundColor = null;
            bar.ButtonInactiveBackgroundColor = null;
            return;
        }
        bool dark = root.ActualTheme == ElementTheme.Dark;
        // The ink and paper of design/tokens (text, and a hover/pressed wash in the text colour).
        var fg = PinkColor("BcTextColor", dark) ?? (dark ? ColorHelper.FromArgb(0xFF, 0xED, 0xEB, 0xE6) : ColorHelper.FromArgb(0xFF, 0x1B, 0x1A, 0x17));
        var muted = PinkColor("BcTextMutedColor", dark) ?? (dark ? ColorHelper.FromArgb(0xFF, 0xB4, 0xB0, 0xA7) : ColorHelper.FromArgb(0xFF, 0x5E, 0x5A, 0x52));
        bar.ButtonBackgroundColor = Colors.Transparent;
        bar.ButtonInactiveBackgroundColor = Colors.Transparent;
        bar.ButtonForegroundColor = fg;
        bar.ButtonHoverForegroundColor = fg;
        bar.ButtonPressedForegroundColor = fg;
        bar.ButtonInactiveForegroundColor = muted;
        bar.ButtonHoverBackgroundColor = ColorHelper.FromArgb(0x18, fg.R, fg.G, fg.B);
        bar.ButtonPressedBackgroundColor = ColorHelper.FromArgb(0x30, fg.R, fg.G, fg.B);
    }
}
