using System.ComponentModel;
using Kalli.Scribe.Services;
using Kalli.Scribe.ViewModels;
using Microsoft.UI;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.UI.ViewManagement;

namespace Kalli.Scribe.Controls;

/// <summary>
/// Settings › Display › Appearance. The theme is set on each window's root element
/// (Application.RequestedTheme cannot change after start-up), on open dialogs and flyouts (they live in the
/// popup layer and don't inherit it), and on the caption buttons. A Windows contrast theme always wins:
/// the roots then ask for Default and the choice is kept for later.
/// The hidden palette, in an app that has one (<see cref="SettingsViewModel.Palette"/>), sits on top of a theme: its light
/// asks for Light and its dark for Dark, and its dictionary (Light and Dark roles) is merged after the app's theme while either is chosen;
/// the roots flip their theme once so every ThemeResource looks again.
/// </summary>
public sealed class ThemeController
{
    private readonly SettingsViewModel _settings;
    private readonly DispatcherQueue _queue;
    private readonly AccessibilitySettings _accessibility = new();
    private readonly List<Window> _windows = [];
    private readonly RootTheme? _override;
    private readonly bool _overrideHidden;
    private ResourceDictionary? _hidden;

    /// <param name="forced">"--theme light|dark|&lt;palette&gt;-light|&lt;palette&gt;-dark" for screenshots: wins over the stored choice (not over contrast).</param>
    public ThemeController(SettingsViewModel settings, DispatcherQueue queue, string? forced)
    {
        _settings = settings;
        Current = this;
        _queue = queue;
        var choice = AppearanceSetting.Parse(forced, settings.Palette);
        _override = choice == Appearance.System ? null : AppearanceSetting.Resolve(choice, false);
        _overrideHidden = AppearanceSetting.IsHidden(choice);
        // Some Windows setups (a service account, a PC without a signed-in desktop session) refuse the contrast
        // setting or its change event: the app then starts without following a contrast theme, rather than not at all.
        try
        {
            _settings.HighContrast = _accessibility.HighContrast;
            // Raised off the UI thread.
            _accessibility.HighContrastChanged += (s, _) => _queue.TryEnqueue(() => _settings.HighContrast = s.HighContrast);
        }
        catch (System.Runtime.InteropServices.COMException e)
        {
            System.Diagnostics.Trace.TraceWarning($"Contrast theme changes can't be followed: {e.Message}");
        }
        _settings.PropertyChanged += OnSettingsChanged;
        ApplyPalette();
    }

    /// <summary>The hidden palette is on the chrome now: the forced theme's, or the setting's; a contrast theme still wins.</summary>
    private bool UsesHidden => _settings.Palette is not null
        && (_override is null ? _settings.UsesHiddenPalette : _overrideHidden && !_settings.HighContrast);

    /// <summary>The app's controller: the last one made (an app makes one).</summary>
    private static ThemeController? Current { get; set; }

    /// <summary>The theme roots and popups ask for now.</summary>
    public ElementTheme Requested => (ElementTheme)(_settings.HighContrast ? RootTheme.Default : _override ?? _settings.RootTheme);

    /// <summary>The theme for a new ContentDialog shown in this app.</summary>
    public static ElementTheme ForDialogs => Current?.Requested ?? ElementTheme.Default;

    /// <summary>Themes a window now and whenever the choice or the contrast theme changes.</summary>
    public void Attach(Window window)
    {
        _windows.Add(window);
        // A theme change still on its way when the window closes reaches a window without an AppWindow: the handler
        // goes with the window.
        Windows.Foundation.TypedEventHandler<FrameworkElement, object> captions = (_, _) => ApplyCaptionButtons(window);
        var root = window.Content as FrameworkElement;
        window.Closed += (_, _) =>
        {
            _windows.Remove(window);
            if (root is not null) root.ActualThemeChanged -= captions;
        };
        if (root is not null) root.ActualThemeChanged += captions;
        Apply(window);
    }

    private void OnSettingsChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is not (nameof(SettingsViewModel.RootTheme) or nameof(SettingsViewModel.UsesHiddenPalette))) return;
        bool repaint = ApplyPalette();
        foreach (var w in _windows.ToList()) Apply(w, repaint);
    }

    /// <summary>Merges the hidden palette in while it is in use, and out otherwise; true when that changed.</summary>
    private bool ApplyPalette()
    {
        var merged = Application.Current.Resources.MergedDictionaries;
        bool want = UsesHidden;
        bool has = _hidden is not null && merged.Contains(_hidden);
        if (want == has) return false;
        if (want)
        {
            _hidden ??= new ResourceDictionary { Source = new Uri(_settings.Palette!.Source) };
            merged.Add(_hidden); // last, so its colour roles win over the app's theme
        }
        else merged.Remove(_hidden!);
        return true;
    }

    private void Apply(Window window, bool repaint = false)
    {
        var theme = Requested;
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

    /// <summary>A colour of the hidden palette for the root's light or dark, while it is in use.</summary>
    private Windows.UI.Color? HiddenColor(string key, bool dark) => UsesHidden ? ThemeColor(_hidden, key, dark) : null;

    /// <summary>A colour role of the app's theme (the last merged dictionary that has it) for light or dark.</summary>
    private static Windows.UI.Color? AppColor(string key, bool dark) =>
        Application.Current.Resources.MergedDictionaries.Reverse().Select(d => ThemeColor(d, key, dark)).FirstOrDefault(c => c is not null);

    private static Windows.UI.Color? ThemeColor(ResourceDictionary? dictionary, string key, bool dark) =>
        dictionary?.ThemeDictionaries.TryGetValue(dark ? "Dark" : "Light", out var d) == true
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
        // The app's text colours (text, and a hover/pressed wash in the text colour).
        var fg = HiddenColor("ScribeTextColor", dark) ?? AppColor("ScribeTextColor", dark) ?? (dark ? Colors.White : Colors.Black);
        var muted = HiddenColor("ScribeTextMutedColor", dark) ?? AppColor("ScribeTextMutedColor", dark) ?? fg;
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
