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
    public static bool IsChooseOutput(Screen current) => current == Screen.ChooseOutput;
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
    /// <summary>The review list's mark: "?" for an open uncertain note, boxed "?" for a very uncertain one, a check once kept.</summary>
    public static bool UncertainOpen(bool kept, bool veryUncertain) => !kept && !veryUncertain;
    public static bool VeryUncertainOpen(bool kept, bool veryUncertain) => !kept && veryUncertain;
    public static bool HasNotes(int count) => count > 0;
    /// <summary>The sidebar icon of a score: the computer (BcIconComputer) for one still on the paired computer, else the score (BcIconScore).</summary>
    public static string LibraryGlyph(bool onComputer) => onComputer ? "\uE977" : "\uEC4F";
    public static bool Both(bool a, bool b) => a && b;
    public static bool Neither(bool a, bool b) => !a && !b;
    /// <summary>A plain bool, for x:Bind function bindings that must return Visibility (Views/Shown.cs).</summary>
    public static bool Is(bool value) => value;
    /// <summary>A percentage in the UI language's spacing ("75%", "75 %").</summary>
    public static string PercentOf(double value) => Percent(value);
    public static bool IsOriginal(Playback.ListeningSource source) => source == Playback.ListeningSource.Original;
    /// <summary>The status row's icon (never colour alone): done, network, attention; the computer when not connected.</summary>
    public static string ConnectionGlyph(Engine.ConnectionState state) => state switch
    {
        Engine.ConnectionState.Connected => "\uE73E",
        Engine.ConnectionState.Reconnecting => "\uE701",
        Engine.ConnectionState.NeedsPairing => "\uE7BA",
        _ => "\uE977",
    };
    /// <summary>Two labels share one cell so a button keeps its size when its label changes: the hidden one is transparent.</summary>
    public static double Opaque(bool shown) => shown ? 1 : 0;
    public static double OpaqueUnless(bool hidden) => hidden ? 0 : 1;
}
