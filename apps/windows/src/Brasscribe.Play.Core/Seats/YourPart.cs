using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Seats;

/// <summary>A part of the shown score, as "your part" is looked up in it.</summary>
/// <param name="Name">The part's own (English) name, as the arranger wrote it.</param>
/// <param name="Chromatic">Semitones from written to sounding (−2 for a B♭ part).</param>
/// <param name="IsPercussion">A percussion part (never the first Solo part).</param>
public sealed record ScorePart(string Name, int Chromatic, bool IsPercussion);

/// <summary>Why the player's part is not their own seat's part: the lineup lacks the seat.</summary>
public enum SeatNotice { None, SameKey, OtherKey, NoPart }

/// <summary>The player's part in one score.</summary>
/// <param name="Index">Index of the part in the score; -1: no part is the player's (every part is shown).</param>
/// <param name="Notice">Set when the lineup lacks the seat and the closest part (or none) stands in.</param>
/// <param name="Lineup">The lineup the seat was looked up in, for the notice's words.</param>
public sealed record YourPartResult(int Index, SeatNotice Notice = SeatNotice.None, Lineup? Lineup = null)
{
    public static readonly YourPartResult Nobody = new(-1);
}

/// <summary>
/// Which part of a score is the player's. In order: the part chosen for this score ("Make this my part"); with a
/// seat, the seat's own part, else the core's closest part for the lineup (<c>seat_part</c>, the one table); with
/// "I conduct or listen", none. Without an answer the score keeps what it always did: the first Solo part.
/// </summary>
public static class YourPart
{
    public static YourPartResult Resolve(ICoreBridge core, SeatChoice choice, Lineup? lineup, IReadOnlyList<ScorePart> parts, string? chosenForScore)
    {
        if (parts.Count == 0) return YourPartResult.Nobody;
        if (chosenForScore is not null && IndexOf(parts, chosenForScore) is var chosen and >= 0) return new(chosen);
        if (choice.IsConductor) return YourPartResult.Nobody;
        var seat = choice.SeatId is { } id ? core.Seats().FirstOrDefault(s => s.Id == id) : null;
        if (seat is null) return new(Legacy(parts));

        // The seat's own part: the full band, and a solo take written for the seat.
        if (IndexOf(parts, seat.Name) is var own and >= 0) return new(own);

        var names = parts.Select(p => p.Name).ToList();
        Lineup[] tries = lineup is { } known ? [known]
            : Lineups.IsQuartet(names) ? [Lineup.Quartet]
            : [Lineup.MinimalBand, Lineup.FullBand];
        foreach (var l in tries)
        {
            if (core.SeatPartFor(Lineups.Core(l), seat.Id) is not { } sp) continue;
            if (sp.Part is null)
            {
                if (lineup is not null) return new(-1, SeatNotice.NoPart, l);
                continue;
            }
            if (IndexOf(parts, sp.Part) is not (var i and >= 0)) continue;
            if (sp.Exact) return new(i);
            string reads = choice.Reads ?? (seat.Reads.Count > 0 ? seat.Reads[0] : "treble");
            // Read in bass clef, every part is at concert pitch: another key does not matter.
            return new(i, sp.SameKey || reads == "bass" ? SeatNotice.SameKey : SeatNotice.OtherKey, l);
        }
        return YourPartResult.Nobody;
    }

    /// <summary>
    /// The one-line notice under the part name: "This small band has no 1st Baritone. Your part here is Euphonium,
    /// the closest: the same key and clef." One sentence per lineup, so Norwegian gets its own definite forms.
    /// </summary>
    public static string? Notice(IStrings s, SeatCatalog seats, SeatChoice choice, YourPartResult result, IReadOnlyList<ScorePart> parts,
        Func<string, string> partName)
    {
        if (result.Notice == SeatNotice.None || result.Lineup is not { } lineup || seats.Find(choice.SeatId) is not { } seat) return null;
        string which = lineup switch
        {
            Lineup.FullBand => "Full",
            Lineup.MinimalBand => "Small",
            Lineup.Quartet => "Quartet",
            _ => throw new ArgumentOutOfRangeException(nameof(result), lineup, null),
        };
        string seatName = seats.Name(seat);
        if (result.Notice == SeatNotice.NoPart) return s.Format($"Seat_Notice_NoPart_{which}", seatName);
        var part = parts[result.Index];
        string mine = partName(part.Name);
        if (result.Notice == SeatNotice.SameKey) return s.Format($"Seat_Notice_SameKey_{which}", seatName, mine);
        bool nb = s.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase) || s.Language.StartsWith("no", StringComparison.OrdinalIgnoreCase);
        string key = Scores.KeyNames.InstrumentKey(part.Chromatic, nb) ?? s["Seat_KeyConcert"];
        return s.Format($"Seat_Notice_OtherKey_{which}", seatName, mine, key);
    }

    /// <summary>Before anyone was asked: the first Solo part that isn't percussion, else the first part.</summary>
    public static int Legacy(IReadOnlyList<ScorePart> parts)
    {
        for (int i = 0; i < parts.Count; i++)
            if (parts[i].Name.Contains("Solo", StringComparison.OrdinalIgnoreCase) && !parts[i].IsPercussion) return i;
        return 0;
    }

    private static int IndexOf(IReadOnlyList<ScorePart> parts, string name)
    {
        for (int i = 0; i < parts.Count; i++)
            if (parts[i].Name == name) return i;
        return -1;
    }
}
