using System.Text.Json;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Scores;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>
/// The lineup names each side speaks: the engine says "full", the Rust core says "band", both say
/// "minimal" and "quartet". Every value is mapped explicitly, so a new lineup cannot fall through
/// to the full band.
/// </summary>
public static class Lineups
{
    /// <summary>The engine's <c>lineup</c> (JobCreate): full, minimal or quartet.</summary>
    public static string Engine(Lineup lineup) => lineup switch
    {
        Lineup.FullBand => "full",
        Lineup.MinimalBand => "minimal",
        Lineup.Quartet => "quartet",
        _ => throw new ArgumentOutOfRangeException(nameof(lineup), lineup, null),
    };

    /// <summary>The core's <c>lineup</c> (bc_arrange_with, bc_arrange_layers_band): band, minimal or quartet.</summary>
    public static string Core(Lineup lineup) => lineup switch
    {
        Lineup.FullBand => "band",
        Lineup.MinimalBand => "minimal",
        Lineup.Quartet => "quartet",
        _ => throw new ArgumentOutOfRangeException(nameof(lineup), lineup, null),
    };

    /// <summary>A lineup name from the engine, the core or a Composition's arrangement; null when unknown.</summary>
    public static Lineup? Parse(string? name) => name switch
    {
        "full" or "band" => Lineup.FullBand,
        "minimal" => Lineup.MinimalBand,
        "quartet" => Lineup.Quartet,
        _ => null,
    };

    /// <summary>The lineup of arrangement options (the engine's names); the full band when empty.</summary>
    public static Lineup Of(ArrangementOptions options) => options.Lineup switch
    {
        "" => Lineup.FullBand,
        var name => Parse(name) ?? throw new ArgumentException($"unknown lineup {name}", nameof(options)),
    };

    /// <summary>The lineup a Composition was arranged for (<c>arrangement.lineup</c>), when it says.</summary>
    public static Lineup? Recorded(Composition? composition) => Parse(ArrangementField(composition, "lineup"));

    /// <summary>The difficulty a Composition was arranged with (<c>arrangement.difficulty</c>), when it says.</summary>
    public static string? RecordedDifficulty(Composition? composition) => ArrangementField(composition, "difficulty");

    /// <summary>The seat a Composition was arranged for (<c>arrangement.seat</c>), when it says.</summary>
    public static string? RecordedSeat(Composition? composition) => ArrangementField(composition, "seat");

    /// <summary>How the seat's part was written (<c>arrangement.reads</c>), when it says.</summary>
    public static string? RecordedReads(Composition? composition) => ArrangementField(composition, "reads");

    /// <summary>Who played the tune (<c>arrangement.lead</c>), when it says.</summary>
    public static string? RecordedLead(Composition? composition) => ArrangementField(composition, "lead");

    /// <summary>
    /// A recording with a soloist over the band (the solo layer and another layer have notes): "Who plays the tune?"
    /// may be asked. A solo take has only the solo layer.
    /// </summary>
    public static bool HasSoloist(Composition? composition, string? profile = null)
    {
        if (profile == "orchestra-with-soloist") return true;
        if (composition is null) return false;
        var sounding = composition.Voices.Where(v => v.Notes.Count > 0).ToList();
        return sounding.Any(v => v.Layer == "solo") && sounding.Any(v => v.Layer is not null and not "solo" and not "drums");
    }

    private static string? ArrangementField(Composition? composition, string field) =>
        composition?.Extra is { } extra
        && extra.TryGetValue("arrangement", out var a) && a.ValueKind == JsonValueKind.Object
        && a.TryGetProperty(field, out var v) && v.ValueKind == JsonValueKind.String
            ? v.GetString()
            : null;

    /// <summary>The quartet's parts in score order (docs/plan/kvartett.md §1.1), one player each.</summary>
    public static readonly IReadOnlyList<string> QuartetParts = ["1st Cornet", "2nd Cornet", "Tenor Horn", "Euphonium"];

    /// <summary>A score whose parts are exactly the quartet's is a quartet (a MusicXML file opened without its Composition).</summary>
    public static bool IsQuartet(IEnumerable<string> partNames) => partNames.SequenceEqual(QuartetParts);

    /// <summary>
    /// A take of one line, with nothing for the other quartet parts to play: the solo profile, a
    /// Composition whose notes are all in the solo (or drums) layer, or a single voice.
    /// </summary>
    public static bool IsSoloTake(Composition? composition, string? profile = null)
    {
        if (profile == "solo") return true;
        if (composition is null) return false;
        var sounding = composition.Voices.Where(v => v.Notes.Count > 0).ToList();
        if (sounding.Count == 0) return false;
        if (sounding.Any(v => v.Layer is not null))
            return sounding.All(v => v.Layer is "solo" or "drums");
        return sounding.Count == 1;
    }
}
