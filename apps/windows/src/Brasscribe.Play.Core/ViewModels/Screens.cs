namespace Brasscribe.Play.Core.ViewModels;

/// <summary>Small functions for x:Bind in the WinUI views (bool binds to Visibility directly).</summary>
public static class Screens
{
    public static bool IsStart(Screen current) => current == Screen.Start;
    public static bool IsSourceKind(Screen current) => current == Screen.SourceKind;
    public static bool IsTranscribing(Screen current) => current == Screen.Transcribing;
    public static bool IsScore(Screen current) => current == Screen.Score;
    public static bool IsFirstRun(Screen current) => current == Screen.FirstRun;
    public static bool IsReview(Screen current) => current == Screen.Review;
    public static bool IsError(Screen current) => current == Screen.Error;
    /// <summary>The library sidebar shows on Home and while a score is made (design/mockups: home, transcribing).</summary>
    public static bool ShowsLibrary(Screen current) => current is Screen.Start or Screen.Transcribing;
    public static bool Not(bool value) => !value;
    public static bool HasText(string? value) => !string.IsNullOrEmpty(value);
    public static bool IsFullScore(int selectedPartIndex) => selectedPartIndex < 0;
    /// <summary>"62%" in English, "62 %" in Norwegian (brand.md, voice rule 8).</summary>
    public static string Percent(double value, string language) =>
        language.StartsWith("nb", StringComparison.OrdinalIgnoreCase) || language.StartsWith("no", StringComparison.OrdinalIgnoreCase)
            ? $"{Math.Round(value)}\u00A0%" : $"{Math.Round(value)}%";
    public static string Percent(double value) => Percent(value, System.Globalization.CultureInfo.CurrentUICulture.Name);
    public static bool IsOriginal(Playback.ListeningSource source) => source == Playback.ListeningSource.Original;
}
