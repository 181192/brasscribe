using Kalli.Scribe.Engine;

namespace Kalli.Scribe.Tab;

public enum MarkKind { Doubt, NoPlace }

/// <summary>Why a note has no place on the instrument.</summary>
public enum NoPlaceWhy { TooLow, TooHigh, Other }

/// <summary>One note under a mark.</summary>
/// <param name="Note">Its place in the tab's notes; null for a "!" read from the page alone, which says no more than a name.</param>
/// <param name="Step">The pitch as it is spelled on the page; null when the page does not spell it.</param>
/// <param name="Name">The note as the boxed words name it ("D1"), for a note the tab staff leaves out.</param>
public sealed record MarkedNote(MarkKind Kind, int? Note, int? String = null, int? Fret = null, string? Step = null, int Alter = 0,
    string? Name = null, NoPlaceWhy Why = NoPlaceWhy.Other);

/// <summary>A column of the tab with a mark above it: one beat of one staff, and the notes there that the mark is for.</summary>
/// <param name="Bar">The measure, counted from 0 as written.</param>
/// <param name="Onset">From the start of the measure, in alphaTab's ticks.</param>
/// <param name="Beat">1 is the first beat of the bar.</param>
/// <param name="Pickup">The column is in the pickup: the notes before the first full bar.</param>
public sealed record TabColumn(int Staff, int Bar, string BarNumber, int Onset, int Beat, IReadOnlyList<MarkedNote> Notes, bool Pickup = false)
{
    /// <summary>A column with a note that has no place shows the boxed "!"; its doubtful notes are still tinted and described.</summary>
    public MarkKind Kind => Notes.Any(n => n.Kind == MarkKind.NoPlace) ? MarkKind.NoPlace : MarkKind.Doubt;
}

/// <summary>
/// The marks of a tab, in reading order, with what the status line says: <see cref="Doubtful"/> notes marked "?" and
/// <see cref="NoPlace"/> notes under a "!", both as they are drawn. <see cref="Unplaced"/> counts marked notes the
/// page has no column for (a note the writer folded into another, or a "!" the page and the data disagree about):
/// they are not drawn, and not in the other two counts.
/// </summary>
public sealed class TabMarks(IReadOnlyList<TabColumn> columns, int doubtful, int noPlace, int unplaced)
{
    /// <summary>A note below this confidence gets a "?": the engine marks the page at the same threshold.</summary>
    public const double UncertainThreshold = TabNote.Doubt;

    public IReadOnlyList<TabColumn> Columns { get; } = columns;
    public int Doubtful { get; } = doubtful;
    public int NoPlace { get; } = noPlace;
    public int Unplaced { get; } = unplaced;

    /// <summary>
    /// The marks from the tab's data: a "?" for every note below <paramref name="threshold"/>, a boxed "!" for every
    /// note without a place. Each is tied to its column through the note index of the page (<paramref name="index"/>).
    ///
    /// Without <paramref name="tab"/> (a saved song when the computer is away) the page itself is read: the confidence
    /// it carries on its doubtful notes, and its boxed words.
    /// </summary>
    public static TabMarks Of(TabIndex index, TabResult? tab, double threshold = UncertainThreshold)
    {
        int staff = index.MarkStaff;
        var found = new Dictionary<(int Bar, int Onset), List<MarkedNote>>();
        // A column's measure number, beat and whether it is in the pickup.
        var places = new Dictionary<(int Bar, int Onset), (string Number, int Beat, bool Pickup)>();
        int unplaced = 0;

        void Add(int bar, string number, int onset, int beat, bool pickup, MarkedNote note)
        {
            places[(bar, onset)] = (number, beat, pickup);
            if (!found.TryGetValue((bar, onset), out var notes)) found[(bar, onset)] = notes = [];
            notes.Add(note);
        }
        void Doubt(TabPiece p) => Add(p.Bar, p.BarNumber, p.Onset, p.Beat, p.Pickup, new MarkedNote(MarkKind.Doubt, p.Note, p.String, p.Fret, p.Step, p.Alter));
        // Where a note starts on the staff with the marks.
        TabPiece? Start(int note)
        {
            var all = index.Of(note);
            return all.FirstOrDefault(p => p.Staff == staff && p.First) ?? all.FirstOrDefault(p => p.Staff == staff);
        }

        if (tab is null)
        {
            // On a notation staff a note without a place is written, and may be in doubt as well: it is under the "!" its
            // boxed words give it, not also under a "?".
            var boxed = index.NoPlace.Where(b => b.Staff == staff).ToList();
            bool UnderABox(TabPiece p) => p.String is null && boxed.Any(b => b.Bar == p.Bar && b.Onset == p.Onset && b.Names.Any(n => n.StartsWith(p.Step, StringComparison.Ordinal)));
            foreach (var p in index.Pieces.Where(p => p.Staff == staff && (p.Confidence ?? double.MaxValue) < threshold && !UnderABox(p))) Doubt(p);
            foreach (var b in boxed)
                foreach (var name in b.Names.Count > 0 ? b.Names : [""])
                    Add(b.Bar, b.BarNumber, b.Onset, b.Beat, b.Pickup, new MarkedNote(MarkKind.NoPlace, null, Name: name.Length > 0 ? name : null));
        }
        else
        {
            var strings = tab.Instrument.Tuning.Strings;
            int? lowest = strings.Count > 0 ? strings.Min(s => s.OpenPitch + tab.Instrument.Capo) : null;
            int? highest = strings.Count > 0 ? strings.Max(s => s.OpenPitch + tab.Instrument.Frets) : null;
            // The boxed words of the page, one name each, in order: where the tab staff has no note to carry an index.
            var boxed = new Queue<(TabNoPlace Box, string Name)>(index.NoPlace.Where(b => b.Staff == staff)
                .SelectMany(b => (b.Names.Count > 0 ? b.Names : [""]).Select(n => (b, n))));
            for (int i = 0; i < tab.Notes.Count; i++)
            {
                var note = tab.Notes[i];
                bool placed = !note.OutOfRange && note.Position is not null;
                if (!placed)
                {
                    var why = lowest is { } low && note.Pitch < low ? NoPlaceWhy.TooLow
                        : highest is { } high && note.Pitch > high ? NoPlaceWhy.TooHigh
                        : NoPlaceWhy.Other;
                    // On a notation staff the note is written, with its index; on a tab staff only the boxed words stand for it.
                    var pieces = index.Of(i);
                    var written = pieces.FirstOrDefault(p => p.First) ?? pieces.FirstOrDefault();
                    (TabNoPlace Box, string Name)? words = boxed.TryDequeue(out var w) ? w : null;
                    string? name = words is { Name.Length: > 0 } named ? named.Name : null;
                    if (written is not null)
                        Add(written.Bar, written.BarNumber, written.Onset, written.Beat, written.Pickup,
                            new MarkedNote(MarkKind.NoPlace, i, Step: written.Step, Alter: written.Alter, Name: name, Why: why));
                    else if (words is { } box)
                        Add(box.Box.Bar, box.Box.BarNumber, box.Box.Onset, box.Box.Beat, box.Box.Pickup, new MarkedNote(MarkKind.NoPlace, i, Name: name, Why: why));
                    else
                        unplaced++;
                }
                else if (note.Confidence < threshold)
                {
                    if (Start(i) is { } start) Doubt(start); else unplaced++;
                }
            }
            unplaced += boxed.Count;
        }
        var columns = found
            .Select(e => { var (number, beat, pickup) = places[e.Key]; return new TabColumn(staff, e.Key.Bar, number, e.Key.Onset, beat, e.Value, pickup); })
            .OrderBy(c => c.Bar).ThenBy(c => c.Onset).ToList();
        // The lines above the tab count what is drawn: a note under a "!" is not also a "?", and a note the page folded into another is neither.
        return new TabMarks(columns, columns.Sum(c => c.Notes.Count(n => n.Kind == MarkKind.Doubt)),
            columns.Sum(c => c.Notes.Count(n => n.Kind == MarkKind.NoPlace)), unplaced);
    }
}
