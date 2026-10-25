namespace Kalli.Scribe.Services;

/// <summary>
/// Settings › Display › Appearance. Match system is the default. <see cref="HiddenLight"/> and <see cref="HiddenDark"/>
/// are Light and Dark in the app's <see cref="HiddenPalette"/>, listed only in an app that has one, once it is unlocked
/// from About. The order is the Appearance box's.
/// </summary>
public enum Appearance { System, Light, Dark, HiddenLight, HiddenDark }

/// <summary>
/// An app's hidden palette: a set of colour roles on top of Light or Dark, unlocked from About. An app without one
/// offers Match system, Light and Dark only.
/// </summary>
/// <param name="Id">How the choice is stored and forced: <c>&lt;id&gt;-light</c> and <c>&lt;id&gt;-dark</c>.</param>
/// <param name="Source">The palette's resource dictionary (an ms-appx URI), merged in while it is in use.</param>
/// <param name="VeryUncertainLight">The very uncertain notes' colour in its light version, when it is not Light's.</param>
public sealed record HiddenPalette(string Id, string Source, string? VeryUncertainLight = null);

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

    /// <summary>The settings.json key of the hidden palette's unlock (this PC only, like the choice).</summary>
    public const string HiddenUnlockedKey = "HiddenPaletteUnlocked";

    /// <summary>An unknown value is Match system, and so is the hidden palette's in an app without it.</summary>
    public static Appearance Parse(string? value, HiddenPalette? palette)
    {
        string? v = value?.Trim().ToLowerInvariant();
        if (v == "light") return Appearance.Light;
        if (v == "dark") return Appearance.Dark;
        if (palette is not null && v == $"{palette.Id}-light") return Appearance.HiddenLight;
        if (palette is not null && v == $"{palette.Id}-dark") return Appearance.HiddenDark;
        return Appearance.System;
    }

    public static string Serialise(Appearance value, HiddenPalette? palette) => value switch
    {
        Appearance.Light => "light",
        Appearance.Dark => "dark",
        Appearance.HiddenLight when palette is not null => $"{palette.Id}-light",
        Appearance.HiddenDark when palette is not null => $"{palette.Id}-dark",
        _ => "system",
    };

    public static bool IsHidden(Appearance choice) => choice is Appearance.HiddenLight or Appearance.HiddenDark;

    /// <summary>The window root's requested theme: Default under a contrast theme and for Match system.</summary>
    public static RootTheme Resolve(Appearance choice, bool highContrast) => highContrast ? RootTheme.Default : choice switch
    {
        Appearance.Light or Appearance.HiddenLight => RootTheme.Light,
        Appearance.Dark or Appearance.HiddenDark => RootTheme.Dark,
        _ => RootTheme.Default,
    };

    /// <summary>The hidden palette is in use: chosen, and no contrast theme on (that still wins).</summary>
    public static bool UsesHidden(Appearance choice, bool highContrast) => IsHidden(choice) && !highContrast;

    /// <summary>The choices the Appearance box lists, in order: the hidden palette's two last, only once it is unlocked.</summary>
    public static IReadOnlyList<Appearance> Choices(bool hiddenUnlocked) =>
        hiddenUnlocked
            ? [Appearance.System, Appearance.Light, Appearance.Dark, Appearance.HiddenLight, Appearance.HiddenDark]
            : [Appearance.System, Appearance.Light, Appearance.Dark];
}

/// <summary>
/// The way into the hidden palette, on About: activating the version <see cref="Taps"/> times in a row, each within <see cref="Window"/>
/// of the one before, unlocks it. A longer pause starts the count again. <see cref="Tap"/> is true exactly once, on the
/// activation that unlocks; after that it stays false, so the confirmation is said only once.
/// </summary>
public sealed class HiddenPaletteUnlock(bool unlocked, TimeProvider? time = null)
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
