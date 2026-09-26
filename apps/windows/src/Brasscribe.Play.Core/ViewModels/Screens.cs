namespace Brasscribe.Play.Core.ViewModels;

/// <summary>Small functions for x:Bind in the WinUI views (bool binds to Visibility directly).</summary>
public static class Screens
{
    public static bool IsStart(Screen current) => current == Screen.Start;
    public static bool IsSourceKind(Screen current) => current == Screen.SourceKind;
    public static bool IsTranscribing(Screen current) => current == Screen.Transcribing;
    public static bool IsScore(Screen current) => current == Screen.Score;
    public static bool Not(bool value) => !value;
    public static bool HasText(string? value) => !string.IsNullOrEmpty(value);
    public static bool IsFullScore(int selectedPartIndex) => selectedPartIndex < 0;
    public static string Percent(double value) => $"{Math.Round(value)} %";
    public static bool IsOriginal(Playback.ListeningSource source) => source == Playback.ListeningSource.Original;
}
