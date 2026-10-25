using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;

namespace Brasscribe.Play.Core.Seats;

/// <summary>
/// "What do you play?": the instrument, then which part (nothing chosen for the player), then, for low brass, the
/// clef they read (the band's own chosen). Nothing is saved here: the first run's Continue and Settings' Save take
/// <see cref="Choice"/> (WCAG 3.2.2).
/// </summary>
public sealed partial class SeatPickerViewModel : ObservableObject
{
    private readonly IStrings _s;

    public SeatPickerViewModel(SeatCatalog catalog, IStrings strings, SeatChoice? current = null)
    {
        Catalog = catalog;
        _s = strings;
        if (current?.SeatId is { } id && catalog.TileOf(id) is { } tile)
        {
            InstrumentIndex = IndexOf(catalog.Tiles, tile);
            if (tile.HasParts) PartIndex = IndexOf(tile.Seats, catalog.Find(id)!);
            if (current.Reads is { } reads && tile.Only.Reads.ToList().IndexOf(reads) is var r and >= 0) ReadsIndex = r;
        }
    }

    public SeatCatalog Catalog { get; }

    /// <summary>The instrument tiles' words, in score order.</summary>
    public IReadOnlyList<InstrumentTile> Tiles => Catalog.Tiles;

    /// <summary>The chosen instrument, -1 until one is chosen.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(Tile), nameof(ShowsParts), nameof(PartChoices), nameof(ShowsReads), nameof(ReadsChoices),
        nameof(Seat), nameof(CanContinue), nameof(ContinueHint))]
    public partial int InstrumentIndex { get; set; } = -1;

    /// <summary>The chosen part of the instrument, -1 until one is chosen (a 3rd cornet is never filed as Solo Cornet).</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(Seat), nameof(CanContinue), nameof(ContinueHint))]
    public partial int PartIndex { get; set; } = -1;

    /// <summary>Index into <see cref="ReadsChoices"/>; 0 is the band's own clef.</summary>
    [ObservableProperty] public partial int ReadsIndex { get; set; }

    partial void OnInstrumentIndexChanged(int oldValue, int newValue)
    {
        if (oldValue == newValue) return;
        PartIndex = -1;
        ReadsIndex = 0;
    }

    public InstrumentTile? Tile => InstrumentIndex >= 0 && InstrumentIndex < Tiles.Count ? Tiles[InstrumentIndex] : null;

    /// <summary>"Which part?" shows once an instrument with several parts is chosen.</summary>
    public bool ShowsParts => Tile is { HasParts: true };

    /// <summary>The parts of the chosen instrument, by the core's full names ("Solo Cornet", "Repiano Cornet").</summary>
    public IReadOnlyList<string> PartChoices => Tile is { HasParts: true } t ? t.Seats.Select(Catalog.Name).ToList() : [];

    /// <summary>"You read" shows for the instruments read in either clef.</summary>
    public bool ShowsReads => Tile is { } t && t.Only.Reads.Count > 1;

    public IReadOnlyList<string> ReadsChoices => Tile is { } t && t.Only.Reads.Count > 1 ? t.Only.Reads.Select(r => Catalog.ReadsLabel(t.Only, r)).ToList() : [];

    /// <summary>The seat chosen so far; null until the instrument (and its part, where there is a choice) is chosen.</summary>
    public SeatInfo? Seat => Tile switch
    {
        null => null,
        { HasParts: false } t => t.Only,
        var t => PartIndex >= 0 && PartIndex < t.Seats.Count ? t.Seats[PartIndex] : null,
    };

    public bool CanContinue => Seat is not null;

    /// <summary>Why Continue can't be pressed yet, as visible text; empty once it can.</summary>
    public string ContinueHint => Tile is null ? _s["Seat_ContinueHint"] : Seat is null ? _s["Seat_ContinueHintPart"] : "";

    /// <summary>The answer; the reading only when it is not the band's own clef.</summary>
    public SeatChoice? Choice
    {
        get
        {
            if (Seat is not { } seat) return null;
            string? reads = seat.Reads.Count > 1 && ReadsIndex > 0 && ReadsIndex < seat.Reads.Count ? seat.Reads[ReadsIndex] : null;
            return new SeatChoice(seat.Id, reads);
        }
    }

    private static int IndexOf<T>(IReadOnlyList<T> list, T item)
    {
        for (int i = 0; i < list.Count; i++)
            if (EqualityComparer<T>.Default.Equals(list[i], item)) return i;
        return -1;
    }
}
