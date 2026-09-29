namespace Brasscribe.Play.Core.Services;

/// <summary>
/// Settings › Display › Appearance (design/system.md §10). Match system is the default. <see cref="Pink"/> is the
/// hidden palette: listed only once it is unlocked from About, and it follows the system's light or dark.
/// </summary>
public enum Appearance { System, Light, Dark, Pink }

/// <summary>The theme a window's root asks for. <see cref="Default"/> lets Windows decide; it maps 1:1 to ElementTheme.</summary>
public enum RootTheme { Default, Light, Dark }

/// <summary>
/// The Appearance choice: how it is stored on this PC (settings.json under LocalAppData, never roamed) and
/// which theme it asks for. A Windows contrast theme always wins: the choice is then ignored, but kept.
/// </summary>
public static class AppearanceSetting
{
    /// <summary>The settings.json key.</summary>
    public const string Key = "Appearance";

    /// <summary>The settings.json key of the Pink unlock (this PC only, like the choice).</summary>
    public const string PinkUnlockedKey = "PinkUnlocked";

    public static Appearance Parse(string? value) => value?.Trim().ToLowerInvariant() switch
    {
        "light" => Appearance.Light,
        "dark" => Appearance.Dark,
        "pink" => Appearance.Pink,
        _ => Appearance.System,
    };

    public static string Serialise(Appearance value) => value switch
    {
        Appearance.Light => "light",
        Appearance.Dark => "dark",
        Appearance.Pink => "pink",
        _ => "system",
    };

    /// <summary>The window root's requested theme: Default under a contrast theme, for Match system and for Pink.</summary>
    public static RootTheme Resolve(Appearance choice, bool highContrast) => highContrast ? RootTheme.Default : choice switch
    {
        Appearance.Light => RootTheme.Light,
        Appearance.Dark => RootTheme.Dark,
        _ => RootTheme.Default,
    };

    /// <summary>The Pink palette is in use: chosen, and no contrast theme on (that still wins).</summary>
    public static bool UsesPink(Appearance choice, bool highContrast) => choice == Appearance.Pink && !highContrast;

    /// <summary>The choices the Appearance box lists, in order: Pink last, only once it is unlocked.</summary>
    public static IReadOnlyList<Appearance> Choices(bool pinkUnlocked) =>
        pinkUnlocked ? [Appearance.System, Appearance.Light, Appearance.Dark, Appearance.Pink] : [Appearance.System, Appearance.Light, Appearance.Dark];
}

/// <summary>
/// The way into Pink, on About: activating the version <see cref="Taps"/> times in a row, each within <see cref="Window"/>
/// of the one before, unlocks it. A longer pause starts the count again. <see cref="Tap"/> is true exactly once, on the
/// activation that unlocks; after that it stays false, so the confirmation is said only once.
/// </summary>
public sealed class PinkUnlock(bool unlocked, TimeProvider? time = null)
{
    public const int Taps = 5;
    public static readonly TimeSpan Window = TimeSpan.FromMilliseconds(1500);

    private readonly TimeProvider _time = time ?? TimeProvider.System;
    private int _count;
    private long _last;

    public bool IsUnlocked { get; private set; } = unlocked;

    public bool Tap()
    {
        if (IsUnlocked) return false;
        long now = _time.GetTimestamp();
        _count = _count > 0 && _time.GetElapsedTime(_last, now) <= Window ? _count + 1 : 1;
        _last = now;
        if (_count < Taps) return false;
        IsUnlocked = true;
        return true;
    }
}
