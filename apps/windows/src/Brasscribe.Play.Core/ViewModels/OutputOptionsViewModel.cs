using Brasscribe.Play.Core.Arrangement;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Seats;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

public enum Lineup { FullBand, MinimalBand, Quartet }
public enum Difficulty { Faithful, Standard, Easier }

/// <summary>
/// "Choose output": lineup, difficulty and key. Apply tries, in order: the Rust core on the device
/// from the layered pipeline's stage files (all three options); a new engine job on the same
/// recording (the engine reuses every cached stage, so only the arrangement runs again); the Rust
/// core re-arranging the lineup of the Composition alone.
/// </summary>
public sealed partial class OutputOptionsViewModel(ICoreBridge core, IAnnouncer announcer, IStrings s) : ObservableObject
{
    /// <summary>Target keys as Brasscribe takes them (concert tonic, by semitone); null keeps the key as recorded.</summary>
    public static readonly string?[] Keys = [null, .. Scores.KeyNames.Tonics];

    [ObservableProperty] public partial Lineup Lineup { get; set; } = Lineup.FullBand;
    [ObservableProperty] public partial Difficulty Difficulty { get; set; } = Difficulty.Faithful;

    /// <summary>
    /// The take is one line (a solo recording): there is no harmony for a quartet to play, so the
    /// quartet card is shown dimmed with the reason and cannot be chosen.
    /// </summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(QuartetAvailable), nameof(QuartetDescription), nameof(QuartetHelpText))]
    public partial bool IsSoloTake { get; set; }

    partial void OnIsSoloTakeChanged(bool value)
    {
        if (value && Lineup == Lineup.Quartet) Lineup = Lineup.FullBand;
        SeatChanged();
    }

    partial void OnLineupChanged(Lineup value) => SeatChanged();

    // ---- The player: their seat for this score, who played a solo take, who plays the tune ----

    /// <summary>The seats (from the core); null or empty: nothing about the player is asked here.</summary>
    public SeatCatalog? Seats { get; set; }

    /// <summary>A part's name in the UI language (the core's table).</summary>
    public Func<string, string> PartLabel { get; set; } = name => name;

    /// <summary>The player's answer in Settings: new takes start from it.</summary>
    public SeatChoice PlayerSeat { get; set; } = SeatChoice.NotSet;

    /// <summary>
    /// The seat this score is written for (a core seat id), or null. It is the score's own: changing Settings
    /// never arranges a score again; only "Who played this?" and Show the score do.
    /// </summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(WhoPlayedIndex))]
    public partial string? Seat { get; set; }

    /// <summary>The clef the seat's part is read in (treble, bass), or null for the band's own.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(KeyDetail))]
    public partial string? Reads { get; set; }

    /// <summary>"Who plays the tune?": the player's part (lead "seat") instead of the lineup's lead.</summary>
    [ObservableProperty] public partial bool TuneOnMyPart { get; set; }

    /// <summary>The recording has a soloist over a band or orchestra (the solo layer): "Who plays the tune?" may be asked.</summary>
    [ObservableProperty] public partial bool HasSoloist { get; set; }

    partial void OnSeatChanged(string? value) => SeatChanged();
    partial void OnHasSoloistChanged(bool value) => SeatChanged();

    private void SeatChanged()
    {
        OnPropertyChanged(nameof(ShowsWhoPlayed));
        OnPropertyChanged(nameof(SoloGivesOnePart));
        OnPropertyChanged(nameof(ShowsLineupChoice));
        OnPropertyChanged(nameof(ShowsTuneChoice));
        OnPropertyChanged(nameof(TuneLineupLabel));
        OnPropertyChanged(nameof(TuneSeatLabel));
        OnPropertyChanged(nameof(FullBandYourPart));
        OnPropertyChanged(nameof(SmallBandYourPart));
        OnPropertyChanged(nameof(QuartetYourPart));
    }

    /// <summary>A new take starts from the player's answer, before anything is sent.</summary>
    public void BeginTake()
    {
        Seat = PlayerSeat.SeatId;
        Reads = PlayerSeat.SeatId is null ? null : PlayerSeat.Reads;
        TuneOnMyPart = false;
    }

    /// <summary>The seats "Who played this?" offers (every brass seat), by the core's names.</summary>
    public IReadOnlyList<SeatInfo> WhoPlayedSeats => Seats?.All.Where(x => x.Reads.Count > 0).ToList() ?? [];

    public IReadOnlyList<string> WhoPlayedChoices => WhoPlayedSeats.Select(x => Seats!.Name(x)).ToList();

    /// <summary>Index into <see cref="WhoPlayedChoices"/>; -1 when nobody is chosen (the take stays a Solo Cornet part).</summary>
    public int WhoPlayedIndex
    {
        get => Seat is { } id ? WhoPlayedSeats.ToList().FindIndex(x => x.Id == id) : -1;
        set
        {
            var seats = WhoPlayedSeats;
            string? id = value >= 0 && value < seats.Count ? seats[value].Id : null;
            if (id == Seat) return;
            // The player's own seat keeps how they read it; a friend's instrument is written the band's way.
            Reads = id is not null && id == PlayerSeat.SeatId ? PlayerSeat.Reads : null;
            Seat = id;
        }
    }

    /// <summary>"Who played this?" on a solo take: a friend may have played it.</summary>
    public bool ShowsWhoPlayed => IsSoloTake && Seats is { IsAvailable: true };

    /// <summary>A solo take written for a seat is one part: the band question goes away, with one line saying why.</summary>
    public bool SoloGivesOnePart => IsSoloTake && Seat is not null;

    public bool ShowsLineupChoice => !SoloGivesOnePart;

    /// <summary>The seat's part in a lineup (the core's table), or null.</summary>
    private string? SeatPartIn(Lineup lineup) => SeatPartRow(lineup)?.Part;

    private SeatPart? SeatPartRow(Lineup lineup)
    {
        if (Seat is not { } seat) return null;
        try { return core.SeatPartFor(Lineups.Core(lineup), seat); }
        catch (CoreBridgeException) { return null; }
    }

    /// <summary>The lead of a band lineup (the core's lineups: Solo Cornet in both).</summary>
    private const string BandLead = "Solo Cornet";

    /// <summary>
    /// "Who plays the tune?" for a soloist recording, in the band lineups only (the quartet keeps the tune on its
    /// 1st Cornet), when the player's part is not the lead and can carry a melody (the core's <c>tune</c>). A seat
    /// that takes the lead part (a trumpet) already has the tune: nothing to choose.
    /// </summary>
    public bool ShowsTuneChoice => !IsSoloTake && HasSoloist && Lineup != Lineup.Quartet && Seats is { } catalog
        && SeatPartRow(Lineup) is { Part: { } part, Takes: null } && part != BandLead && catalog.CarriesTune(part);

    /// <summary>"Solo Cornet (as usual)".</summary>
    public string TuneLineupLabel => s.Format("Output_TuneLineup", PartLabel(BandLead));

    /// <summary>"You: Euphonium".</summary>
    public string TuneSeatLabel => SeatPartIn(Lineup) is { } part ? s.Format("Output_TuneSeat", PartLabel(part)) : "";

    /// <summary>"Your part: Euphonium" on a lineup card, so the player knows before Show the score; empty without a seat.</summary>
    private string YourPartOn(Lineup lineup) => Seat is null ? ""
        : SeatPartIn(lineup) is { } part ? s.Format("Output_YourPart", PartLabel(part))
        : s["Output_YourPartNone"];

    public string FullBandYourPart => YourPartOn(Lineup.FullBand);
    public string SmallBandYourPart => YourPartOn(Lineup.MinimalBand);
    public string QuartetYourPart => IsSoloTake ? "" : YourPartOn(Lineup.Quartet);

    /// <summary>The seat, reading and lead the options carry: a solo take for a seat always has the tune on it.</summary>
    private (string? Seat, string? Reads, string? Lead) SeatOptions()
    {
        if (Seat is not { } seat) return (null, null, null);
        string? lead = IsSoloTake || TuneOnMyPart && ShowsTuneChoice ? "seat" : null;
        return (seat, Reads, lead);
    }

    public bool QuartetAvailable => !IsSoloTake;

    /// <summary>
    /// A whole-band recording (brass band, pop or rock): it is arranged for the small band or the
    /// quartet only, so the full-band card is dimmed with the reason and a full band goes to the small band.
    /// </summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(FullAvailable), nameof(FullDescription), nameof(FullHelpText), nameof(AppliedLineup))]
    public partial bool IsBandTake { get; set; }

    partial void OnIsBandTakeChanged(bool value)
    {
        if (value && Lineup == Lineup.FullBand) (Lineup, _fullPutBack) = (Lineup.MinimalBand, true);
        else if (!value && _fullPutBack && Lineup == Lineup.MinimalBand) Lineup = Lineup.FullBand;
        if (!value) _fullPutBack = false;
    }

    /// <summary>The full band was moved to the small band for a band take (not chosen), so the next take gets it back.</summary>
    private bool _fullPutBack;

    public bool FullAvailable => !IsBandTake;

    /// <summary>The full-band card's second line: what it is, or why it can't be chosen.</summary>
    public string FullDescription => IsBandTake ? s["Output_FullNotYet"] : s["Output_FullBody"];

    /// <summary>The reason for screen readers when the card can't be chosen; empty otherwise.</summary>
    public string FullHelpText => IsBandTake ? s["Output_FullNotYet"] : "";

    /// <summary>The lineup the arranger makes for <paramref name="lineup"/>: a band take never gets the full band.</summary>
    public Lineup Made(Lineup lineup) => IsBandTake && lineup == Lineup.FullBand ? Lineup.MinimalBand : lineup;

    /// <summary>The quartet card's second line: what it is, or why it can't be chosen.</summary>
    public string QuartetDescription => IsSoloTake ? s["Output_QuartetNeedsGroup"] : s["Output_QuartetBody"];

    /// <summary>The reason for screen readers when the card can't be chosen; empty otherwise.</summary>
    public string QuartetHelpText => IsSoloTake ? s["Output_QuartetNeedsGroup"] : "";

    /// <summary>
    /// A lineup card was chosen. The quartet on a solo take is refused with the reason said aloud;
    /// false tells the page to put the selection back.
    /// </summary>
    public bool TryChooseLineup(Lineup lineup)
    {
        if (lineup == Lineup.Quartet && !QuartetAvailable)
        {
            announcer.Announce(s["Output_QuartetNeedsGroup"], AnnouncementKind.Important);
            return false;
        }
        if (lineup == Lineup.FullBand && !FullAvailable)
        {
            announcer.Announce(s["Output_FullNotYet"], AnnouncementKind.Important);
            return false;
        }
        _fullPutBack = false;
        Lineup = lineup;
        return true;
    }

    /// <summary>Index into <see cref="Keys"/>.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(KeyLabel), nameof(KeyDetail))]
    public partial int KeyIndex { get; set; }

    /// <summary>The key the recording is in (from the Composition), when known.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(KeyLabel), nameof(KeyDetail))]
    public partial (int PitchClass, bool Minor)? RecordedKey { get; set; }

    /// <summary>The player's instrument: semitones from written to sounding (−2 for B♭ cornet), null for C instruments.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(KeyDetail))]
    public partial int? InstrumentChromatic { get; set; }

    /// <summary>The instrument in <see cref="InstrumentChromatic"/> is the player's own part (they said what they play).</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(KeyDetail))]
    public partial bool InstrumentIsYours { get; set; }

    /// <summary>Sets the recorded key and the player's instrument from a loaded score.</summary>
    public void SetScoreContext(Scores.Composition? composition, int? chromatic, bool yours = false)
    {
        InstrumentIsYours = yours;
        RecordedKey = composition?.Keys.OrderBy(k => k.Tick).FirstOrDefault() is { } k
            ? (Scores.KeyNames.TonicOf(k.Fifths, k.Mode == "minor"), k.Mode == "minor")
            : null;
        InstrumentChromatic = chromatic is { } c && ((c % 12) + 12) % 12 != 0 ? c : null;
    }

    private bool Nb => s.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase) || s.Language.StartsWith("no", StringComparison.OrdinalIgnoreCase);

    /// <summary>The concert key chosen (or recorded), when it can be said.</summary>
    private (int PitchClass, bool Minor)? ConcertKey =>
        Keys[Math.Clamp(KeyIndex, 0, Keys.Length - 1)] is { } tonic
            ? (Scores.KeyNames.PitchClassOf(tonic), RecordedKey?.Minor ?? false)
            : RecordedKey;

    /// <summary>"C major (concert)", or "As recorded" when the recording's key is not known.</summary>
    public string KeyLabel => ConcertKey is { } k
        ? s.Format("Output_KeyConcert", Scores.KeyNames.Name(k.PitchClass, k.Minor, Nb))
        : s["Key_AsRecorded"];

    /// <summary>"As recorded · D major for B♭ instruments" (usability review 2, P2-3).</summary>
    public string KeyDetail
    {
        get
        {
            var parts = new List<string>();
            if (KeyIndex == 0) parts.Add(s["Key_AsRecorded"]);
            // Read in bass clef, the player's part is at concert pitch: "D major, as it sounds".
            if (ConcertKey is { } sounding && InstrumentIsYours && Reads == "bass")
            {
                parts.Add(s.Format("Output_KeyAsItSounds", Scores.KeyNames.Name(sounding.PitchClass, sounding.Minor, Nb)));
                return string.Join(" · ", parts);
            }
            if (ConcertKey is { } k && InstrumentChromatic is { } c && Scores.KeyNames.InstrumentKey(c, Nb) is { } instrument)
                parts.Add(InstrumentIsYours
                    ? s.Format("Output_KeyOnYourPart", Scores.KeyNames.Name(Scores.KeyNames.WrittenOf(k.PitchClass, c), k.Minor, Nb))
                    : s.Format("Output_KeyWritten", Scores.KeyNames.Name(Scores.KeyNames.WrittenOf(k.PitchClass, c), k.Minor, Nb), instrument));
            return parts.Count > 0 ? string.Join(" · ", parts) : s["Output_KeyConcertDetail"];
        }
    }

    /// <summary>A semitone lower (the "Lower" button).</summary>
    [RelayCommand]
    private void KeyDown() => StepKey(-1);

    /// <summary>A semitone higher (the "Higher" button).</summary>
    [RelayCommand]
    private void KeyUp() => StepKey(+1);

    private void StepKey(int semitones)
    {
        int current = ConcertKey?.PitchClass ?? 0;
        int next = ((current + semitones) % 12 + 12) % 12;
        KeyIndex = RecordedKey is { } r && r.PitchClass == next ? 0 : 1 + next;
    }

    /// <summary>The options the shown score was arranged with; "Show the score" arranges only when these change.</summary>
    public ArrangementOptions Applied { get; set; } = ArrangementOptions.Default;

    /// <summary>The lineup of the score being shown (what <see cref="Applied"/> says).</summary>
    public Lineup AppliedLineup => Made(Lineups.Parse(Applied.Lineup) ?? Lineup.FullBand);

    /// <summary>
    /// A score was opened from "Your scores": the choices follow what it was arranged with, so
    /// "Show the score" and a changed note keep its lineup.
    /// </summary>
    public void ShowingSaved(Lineup? lineup, string? difficulty, Scores.Composition? composition = null)
    {
        var chosen = lineup ?? Lineup.FullBand;
        if (chosen == Lineup.Quartet && IsSoloTake) chosen = Lineup.FullBand;
        Lineup = Made(chosen);
        _fullPutBack = Lineup != chosen;
        Difficulty = difficulty switch { "standard" => Difficulty.Standard, "easier" => Difficulty.Easier, _ => Difficulty.Faithful };
        KeyIndex = 0;
        // The seat it was written for, as recorded; a score from before anyone was asked has none.
        Reads = Lineups.RecordedReads(composition);
        Seat = Lineups.RecordedSeat(composition);
        TuneOnMyPart = Lineups.RecordedLead(composition) == "seat" && !IsSoloTake;
        Applied = Options;
    }

    /// <summary>A score just made: the choices are what it was made with.</summary>
    public void ShowingMade(ArrangementOptions options)
    {
        Reads = options.Reads;
        Seat = options.Seat;
        TuneOnMyPart = options.Lead == "seat" && !IsSoloTake;
        Applied = options;
    }

    /// <summary>Raised when the score can be shown as it is (nothing changed).</summary>
    public event EventHandler? ShowScoreRequested;

    /// <summary>"Show the score": arranges again only when a choice changed (WCAG 3.2.2), otherwise just shows it.</summary>
    [RelayCommand]
    private async Task ShowScore(Scores.Composition? composition)
    {
        if (Options == Applied)
        {
            ShowScoreRequested?.Invoke(this, EventArgs.Empty);
            return;
        }
        await ApplyCommand.ExecuteAsync(composition);
    }

    /// <summary>Set by the app when the score came from an engine job it can re-run.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(DifficultyAvailable), nameof(KeyAvailable), nameof(UnavailableText))]
    public partial bool HasEngineJob { get; set; }

    /// <summary>
    /// Set by the app when the layered pipeline's stage files can be had (from the engine job or a
    /// local folder); with the native core they arrange on the device.
    /// </summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(DifficultyAvailable), nameof(KeyAvailable), nameof(UnavailableText), nameof(CanArrangeOnDevice))]
    public partial Func<CancellationToken, Task<LayerInputs?>>? LayerSource { get; set; }

    /// <summary>Title the on-device arrangement writes into the score.</summary>
    public string Title { get; set; } = "Draft";

    public bool CanArrangeOnDevice => core.IsNative && LayerSource is not null;
    public bool CanArrange => core.IsNative || HasEngineJob;
    public bool DifficultyAvailable => HasEngineJob || CanArrangeOnDevice;
    public bool KeyAvailable => HasEngineJob || CanArrangeOnDevice;
    public string UnavailableText => DifficultyAvailable ? "" : s["Output_NeedsEngine"];

    [ObservableProperty] public partial string? StatusText { get; set; }

    public ArrangementOptions Options
    {
        get
        {
            var (seat, reads, lead) = SeatOptions();
            return new(
                Lineups.Engine(Lineup),
                Difficulty switch { Difficulty.Standard => "standard", Difficulty.Easier => "easier", _ => "faithful" },
                Keys[Math.Clamp(KeyIndex, 0, Keys.Length - 1)] is { } tonic && RecordedKey is { Minor: true } ? tonic + "m" : Keys[Math.Clamp(KeyIndex, 0, Keys.Length - 1)],
                Seat: seat, Reads: reads, Lead: lead);
        }
    }

    /// <summary>Raised with the options when the engine should arrange again.</summary>
    public event EventHandler<ArrangementOptions>? RearrangeRequested;

    /// <summary>Raised with MusicXML arranged on the device from the Composition.</summary>
    public event EventHandler<string>? Arranged;

    /// <summary>Raised with a score arranged on the device from the layer inputs (new MusicXML and Composition).</summary>
    public event EventHandler<BandArrangement>? ArrangedBand;

    [RelayCommand]
    private async Task Apply(Scores.Composition? composition)
    {
        if (CanArrangeOnDevice && await TryArrangeOnDeviceAsync()) return;
        if (HasEngineJob)
        {
            StatusText = s["Output_Rearranging"];
            announcer.Announce(StatusText);
            Applied = Options;
            RearrangeRequested?.Invoke(this, Options);
            return;
        }
        if (composition is null) return;
        if (!core.IsNative)
        {
            StatusText = s["Output_NeedsCore"];
            announcer.Announce(StatusText, AnnouncementKind.Important);
            return;
        }
        try
        {
            var options = Options;
            var xml = core.ArrangeMusicXmlWith(composition, options);
            if (xml is null) return;
            Applied = options;
            StatusText = s["Output_Ready"];
            announcer.Announce(StatusText, AnnouncementKind.Important);
            Arranged?.Invoke(this, xml);
        }
        catch (CoreBridgeException e)
        {
            StatusText = EngineErrors.CoreMessage(e.Message, s);
            announcer.Announce(StatusText, AnnouncementKind.Important);
        }
    }

    /// <summary>False when the layer inputs cannot be had, so the next way is tried.</summary>
    private async Task<bool> TryArrangeOnDeviceAsync()
    {
        StatusText = s["Output_Rearranging"];
        announcer.Announce(StatusText);
        LayerInputs? inputs;
        try
        {
            inputs = await LayerSource!(CancellationToken.None);
        }
        catch (Exception e) when (e is EngineException or IOException or InvalidDataException or NotSupportedException or UnauthorizedAccessException)
        {
            inputs = null;
        }
        if (inputs is null) return false;
        try
        {
            var options = Options;
            var band = await Task.Run(() => core.ArrangeLayersBand(inputs, Title, options));
            if (band is null) return false;
            Applied = options;
            StatusText = s["Output_Ready"];
            announcer.Announce(StatusText, AnnouncementKind.Important);
            ArrangedBand?.Invoke(this, band);
        }
        catch (CoreBridgeException e)
        {
            StatusText = EngineErrors.CoreMessage(e.Message, s);
            announcer.Announce(StatusText, AnnouncementKind.Important);
        }
        return true;
    }
}
