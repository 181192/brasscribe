namespace Brasscribe.Play.Core.Services;

/// <summary>Settings › Display › Appearance (design/system.md §10). Match system is the default.</summary>
public enum Appearance { System, Light, Dark }

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

    public static Appearance Parse(string? value) => value?.Trim().ToLowerInvariant() switch
    {
        "light" => Appearance.Light,
        "dark" => Appearance.Dark,
        _ => Appearance.System,
    };

    public static string Serialise(Appearance value) => value switch
    {
        Appearance.Light => "light",
        Appearance.Dark => "dark",
        _ => "system",
    };

    /// <summary>The window root's requested theme: Default under a contrast theme and for Match system.</summary>
    public static RootTheme Resolve(Appearance choice, bool highContrast) => highContrast ? RootTheme.Default : choice switch
    {
        Appearance.Light => RootTheme.Light,
        Appearance.Dark => RootTheme.Dark,
        _ => RootTheme.Default,
    };
}
