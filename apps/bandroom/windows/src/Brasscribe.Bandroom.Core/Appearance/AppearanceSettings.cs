using CommunityToolkit.Mvvm.ComponentModel;

namespace Brasscribe.Bandroom.Core.Appearance;

/// <summary>The Appearance choice in Settings (design/system.md §10). Match system is the default.</summary>
public enum AppearanceChoice { System, Light, Dark }

/// <summary>The theme the windows get: Default follows Windows (and every contrast theme).</summary>
public enum ResolvedTheme { Default, Light, Dark }

public static class AppearanceRules
{
    /// <summary>The choices in the order the picker lists them.</summary>
    public static IReadOnlyList<AppearanceChoice> Order { get; } = [AppearanceChoice.System, AppearanceChoice.Light, AppearanceChoice.Dark];

    /// <summary>"light" and "dark" (any case, trimmed); anything else, missing or unreadable, is Match system.</summary>
    public static AppearanceChoice Parse(string? value) => value?.Trim().ToLowerInvariant() switch
    {
        "light" => AppearanceChoice.Light,
        "dark" => AppearanceChoice.Dark,
        _ => AppearanceChoice.System,
    };

    public static string Serialize(AppearanceChoice choice) => choice switch
    {
        AppearanceChoice.Light => "light",
        AppearanceChoice.Dark => "dark",
        _ => "system",
    };

    /// <summary>A contrast theme always wins: the choice is ignored while it is on, and kept for when it's off.</summary>
    public static ResolvedTheme Resolve(AppearanceChoice choice, bool highContrast) => highContrast ? ResolvedTheme.Default : choice switch
    {
        AppearanceChoice.Light => ResolvedTheme.Light,
        AppearanceChoice.Dark => ResolvedTheme.Dark,
        _ => ResolvedTheme.Default,
    };

    /// <summary>The option's label: Match system / Light / Dark.</summary>
    public static string Label(IStrings s, AppearanceChoice choice) => s[choice switch
    {
        AppearanceChoice.Light => "Appearance_Light",
        AppearanceChoice.Dark => "Appearance_Dark",
        _ => "Appearance_System",
    }];
}

/// <summary>Stores the choice on this PC only (a one-word file in Bandroom's state folder), never roamed.</summary>
public sealed class AppearanceStore(string filePath)
{
    public string FilePath { get; } = filePath;

    public AppearanceChoice Load()
    {
        try { return File.Exists(FilePath) ? AppearanceRules.Parse(File.ReadAllText(FilePath)) : AppearanceChoice.System; }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return AppearanceChoice.System; }
    }

    /// <returns>False when the file can't be written; the choice still applies until Bandroom quits.</returns>
    public bool Save(AppearanceChoice choice)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
            File.WriteAllText(FilePath, AppearanceRules.Serialize(choice));
            return true;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { return false; }
    }
}

/// <summary>
/// The Appearance row: the choice (stored at once), whether a contrast theme is on, the theme every window
/// gets, and the one line that says the contrast theme decides. Applying is instant: listen to ThemeChanged.
/// </summary>
public sealed partial class AppearanceViewModel : ObservableObject
{
    private readonly IStrings _s;
    private readonly AppearanceStore? _store;
    private ResolvedTheme _lastResolved;

    /// <param name="strings">The copy.</param>
    /// <param name="store">Null keeps the choice in memory only (screenshots with --theme).</param>
    /// <param name="highContrast">Whether a Windows contrast theme is on now.</param>
    /// <param name="initial">Overrides the stored choice (--theme); not saved unless changed.</param>
    public AppearanceViewModel(IStrings strings, AppearanceStore? store, bool highContrast, AppearanceChoice? initial = null)
    {
        _s = strings;
        _store = store;
        _choice = initial ?? store?.Load() ?? AppearanceChoice.System;
        _highContrast = highContrast;
        _lastResolved = Resolved;
        Options = AppearanceRules.Order.Select(c => AppearanceRules.Label(strings, c)).ToList();
    }

    /// <summary>"Appearance" / «Utseende».</summary>
    public string Header => _s["Appearance_Title"];

    /// <summary>Match system, Light, Dark, in <see cref="AppearanceRules.Order"/>.</summary>
    public IReadOnlyList<string> Options { get; }

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(SelectedIndex), nameof(Resolved))]
    private AppearanceChoice _choice;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(Resolved), nameof(ContrastNote), nameof(ShowsContrastNote))]
    private bool _highContrast;

    /// <summary>The picker's selected index; out-of-range values (-1 while the list is rebuilt) are ignored.</summary>
    public int SelectedIndex
    {
        get => AppearanceRules.Order.ToList().IndexOf(Choice);
        set { if (value >= 0 && value < AppearanceRules.Order.Count) Choice = AppearanceRules.Order[value]; }
    }

    /// <summary>The theme every window has now.</summary>
    public ResolvedTheme Resolved => AppearanceRules.Resolve(Choice, HighContrast);

    public bool ShowsContrastNote => HighContrast;

    /// <summary>"Your contrast theme is on, so Windows chooses the colours." while one is on; else empty.</summary>
    public string ContrastNote => HighContrast ? _s["Appearance_Contrast"] : "";

    /// <summary>The theme the windows should have changed (a new choice, or a contrast theme on or off).</summary>
    public event Action<ResolvedTheme>? ThemeChanged;

    partial void OnChoiceChanged(AppearanceChoice value)
    {
        _store?.Save(value);
        RaiseIfResolvedChanged();
    }

    partial void OnHighContrastChanged(bool value) => RaiseIfResolvedChanged();

    private void RaiseIfResolvedChanged()
    {
        if (Resolved == _lastResolved) return;
        _lastResolved = Resolved;
        ThemeChanged?.Invoke(_lastResolved);
    }
}
