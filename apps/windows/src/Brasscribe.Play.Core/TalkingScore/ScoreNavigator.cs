namespace Brasscribe.Play.Core.TalkingScore;

/// <summary>Result of a navigation command: the text to expose (and announce) and whether the cursor moved.</summary>
public sealed record NavigationResult(string Text, bool Moved);

/// <summary>
/// Cursor over a <see cref="TalkingScoreDocument"/> implementing the navigation commands of the
/// talking-score spec §5 (note, beat, bar, part, uncertain note, go to bar, read bar, where am I).
/// Platform views stay thin: they map keys and gestures to these methods and expose <see cref="Text"/>.
/// </summary>
public sealed class ScoreNavigator
{
    private readonly TalkingScoreDocument _doc;
    private AnnounceContext _context = new();
    private TsEvent? _synthetic; // a held or collapsed-rest event made by the navigator

    public ScoreNavigator(TalkingScoreDocument doc, TalkingScoreSettings? settings = null)
    {
        _doc = doc;
        Settings = settings ?? new TalkingScoreSettings();
        if (doc.Parts.Count > 0 && doc.Parts[0].Bars.Count > 0) Text = Land(0, 0, 0, byBar: true);
    }

    public TalkingScoreDocument Document => _doc;
    public TalkingScoreSettings Settings { get; set; }
    public int PartIndex { get; private set; }
    public int BarIndex { get; private set; }
    public int EventIndex { get; private set; }
    /// <summary>The announcement for the current position; exposed as the score's accessible value.</summary>
    public string Text { get; private set; } = "";

    public event EventHandler<string>? Moved;

    public TsPart Part => _doc.Parts[PartIndex];
    public TsBar Bar => Part.Bars[BarIndex];
    public TsEvent? Event => _synthetic ?? (EventIndex < Bar.Events.Count ? Bar.Events[EventIndex] : null);
    /// <summary>Ticks from the start of the bar of the current position.</summary>
    public int TickInBar { get; private set; }

    private Lexicon L => Settings.Nb ? Lexicon.Nb : Lexicon.En;

    // ---- notes ----

    public NavigationResult NextNote()
    {
        int p = PartIndex, b = BarIndex, e = EventIndex;
        if (_synthetic is { Kind: EventKind.BarRest, Bars: > 1 } rest) { b += rest.Bars - 1; e = int.MaxValue - 1; }
        while (true)
        {
            e++;
            if (b >= Part.Bars.Count) return Stay(EndOfPart);
            if (e >= _doc.Parts[p].Bars[b].Events.Count)
            {
                b++;
                e = -1;
                if (b >= _doc.Parts[p].Bars.Count) return Stay(EndOfPart);
                continue;
            }
            var ev = _doc.Parts[p].Bars[b].Events[e];
            if (IsTieContinuation(ev)) continue;
            return Go(p, b, e);
        }
    }

    public NavigationResult PreviousNote()
    {
        int p = PartIndex, b = BarIndex, e = EventIndex;
        if (_synthetic is { Kind: EventKind.Held }) e++;
        while (true)
        {
            e--;
            if (e < 0)
            {
                b--;
                if (b < 0) return Stay(StartOfPart);
                e = _doc.Parts[p].Bars[b].Events.Count;
                continue;
            }
            var ev = _doc.Parts[p].Bars[b].Events[e];
            if (IsTieContinuation(ev)) continue;
            // Land on the first bar of a run of whole-bar rests.
            if (ev.Kind == EventKind.BarRest)
                while (b > 0 && IsRestBar(_doc.Parts[p].Bars[b - 1])) b--;
            return Go(p, b, ev.Kind == EventKind.BarRest ? 0 : e);
        }
    }

    // ---- beats ----

    public NavigationResult NextBeat() => StepBeat(+1);
    public NavigationResult PreviousBeat() => StepBeat(-1);

    private NavigationResult StepBeat(int dir)
    {
        int beatTicks = BeatTicks(Bar.Time);
        int beat = TickInBar / beatTicks + dir;
        int b = BarIndex;
        if (TickInBar % beatTicks != 0 && dir < 0) beat++; // from an off-beat, "previous" is this beat
        if (beat < 0)
        {
            if (--b < 0) return Stay(StartOfPart);
            beat = BarBeats(Part.Bars[b]) - 1;
        }
        else if (beat >= BarBeats(Bar))
        {
            if (++b >= Part.Bars.Count) return Stay(EndOfPart);
            beat = 0;
        }
        return GoToTick(PartIndex, b, beat * BeatTicks(Part.Bars[b].Time), byBar: false);
    }

    // ---- bars ----

    public NavigationResult NextBar()
    {
        int step = _synthetic is { Kind: EventKind.BarRest, Bars: > 1 } r ? r.Bars : 1;
        return BarIndex + step < Part.Bars.Count ? Go(PartIndex, BarIndex + step, 0, byBar: true) : Stay(EndOfPart);
    }

    public NavigationResult PreviousBar() =>
        BarIndex > 0 ? Go(PartIndex, BarIndex - 1, 0, byBar: true) : Stay(StartOfPart);

    public NavigationResult FirstBar() => Go(PartIndex, 0, 0, byBar: true);
    public NavigationResult LastBar() => Go(PartIndex, Part.Bars.Count - 1, 0, byBar: true);

    public NavigationResult GoToBar(int number)
    {
        int i = Part.Bars.FindIndex(b => b.Number == number);
        if (i < 0) return Stay(Settings.Nb ? $"Takt {number} finnes ikke" : $"There is no bar {number}");
        return Go(PartIndex, i, 0, byBar: true);
    }

    // ---- parts ----

    public NavigationResult NextPart() => StepPart(+1);
    public NavigationResult PreviousPart() => StepPart(-1);

    public NavigationResult GoToPart(int index)
    {
        if (index < 0 || index >= _doc.Parts.Count) return Stay(Text);
        return GoToTick(index, Math.Min(BarIndex, _doc.Parts[index].Bars.Count - 1), TickInBar, byBar: false);
    }

    private NavigationResult StepPart(int dir)
    {
        int p = PartIndex + dir;
        if (p < 0 || p >= _doc.Parts.Count) return Stay(dir > 0 ? LastPart : FirstPart);
        return GoToPart(p);
    }

    // ---- uncertain notes ----

    public NavigationResult NextUncertain() => StepUncertain(+1);
    public NavigationResult PreviousUncertain() => StepUncertain(-1);

    private NavigationResult StepUncertain(int dir)
    {
        var part = Part;
        int b = BarIndex, e = _synthetic is null ? EventIndex : dir > 0 ? EventIndex - 1 : EventIndex;
        while (true)
        {
            e += dir;
            if (e < 0 || e >= part.Bars[b].Events.Count)
            {
                b += dir;
                if (b < 0 || b >= part.Bars.Count) return Stay(Settings.Nb ? "Ingen flere usikre noter" : "No more uncertain notes");
                e = dir > 0 ? -1 : part.Bars[b].Events.Count;
                continue;
            }
            var ev = part.Bars[b].Events[e];
            if (ev.IsUncertain && !IsTieContinuation(ev)) return Go(PartIndex, b, e);
        }
    }

    /// <summary>Moves to one event (the review list).</summary>
    public NavigationResult GoToEvent(int part, int barIndex, int eventIndex)
    {
        if (part < 0 || part >= _doc.Parts.Count || barIndex < 0 || barIndex >= _doc.Parts[part].Bars.Count) return Stay(Text);
        return Go(part, barIndex, eventIndex);
    }

    /// <summary>Marks the current note as checked; returns the number of uncertain notes left in the score.</summary>
    public int MarkChecked()
    {
        if (Event is { } ev && _synthetic is null) ev.Checked = true;
        Text = Announce(Part, BarIndex, Event!, byBar: false, updateContext: false);
        return UncertainCount;
    }

    public int UncertainCount => _doc.Parts.Sum(p => p.Bars.Sum(b => b.Events.Count(e => e.IsUncertain && !IsTieContinuation(e))));

    // ---- reading ----

    /// <summary>Every event in the current bar in brief form (the "Read bar" command).</summary>
    public string ReadBar()
    {
        var events = Bar.Events.Where(e => !IsTieContinuation(e) || e == Bar.Events.FirstOrDefault()).ToList();
        return Announcer.ReadBar(ToAnnouncePart(Part), ToAnnounceBar(BarIndex, byBar: false), events, Settings);
    }

    /// <summary>The current event at full verbosity (the "Where am I" command).</summary>
    public string WhereAmI()
    {
        var full = Settings with { Verbosity = Verbosity.Full };
        return Announcer.Announce(ToAnnouncePart(Part), ToAnnounceBar(BarIndex, byBar: true) with { EnteringRegion = false, ATempo = false },
            Event ?? new TsEvent { Kind = EventKind.Rest, Type = "quarter", Pos = new TsPos(1) },
            new AnnounceContext(), full, byBar: true);
    }

    /// <summary>Switches written/concert pitch and returns the mode-change announcement.</summary>
    public string SetPitchMode(PitchMode mode)
    {
        Settings = Settings with { PitchMode = mode };
        _context = _context with { PitchMode = mode };
        return Announcer.Announce(ToAnnouncePart(Part), ToAnnounceBar(BarIndex, false), new TsEvent { Kind = EventKind.ModeChange },
            _context, Settings);
    }

    /// <summary>Recording time of the current position, when the score knows it.</summary>
    public double? TimeSeconds => Event?.TimeS;

    // ---- internals ----

    private string EndOfPart => Settings.Nb ? "Slutten av stemmen" : "End of part";
    private string StartOfPart => Settings.Nb ? "Starten av stemmen" : "Start of part";
    private string LastPart => Settings.Nb ? "Siste stemme" : "Last part";
    private string FirstPart => Settings.Nb ? "Første stemme" : "First part";

    private NavigationResult Stay(string message) => new(message, false);

    private NavigationResult Go(int p, int b, int e, bool byBar = false)
    {
        Text = Land(p, b, e, byBar);
        Moved?.Invoke(this, Text);
        return new NavigationResult(Text, true);
    }

    private string Land(int p, int b, int e, bool byBar)
    {
        PartIndex = p;
        BarIndex = b;
        var bar = _doc.Parts[p].Bars[b];
        _synthetic = null;
        if (bar.Events.Count == 0)
        {
            EventIndex = 0;
            TickInBar = 0;
            _synthetic = new TsEvent { Kind = EventKind.BarRest, Bars = 1 };
            return Announce(_doc.Parts[p], b, _synthetic, byBar);
        }
        EventIndex = Math.Clamp(e, 0, bar.Events.Count - 1);
        var ev = bar.Events[EventIndex];
        TickInBar = ev.Tick;
        if (ev.Kind == EventKind.BarRest)
        {
            int run = 1;
            while (b + run < _doc.Parts[p].Bars.Count && IsRestBar(_doc.Parts[p].Bars[b + run])) run++;
            if (run > 1)
            {
                _synthetic = new TsEvent { Kind = EventKind.BarRest, Bars = run };
                return Announce(_doc.Parts[p], b, _synthetic, byBar);
            }
        }
        return Announce(_doc.Parts[p], b, ev, byBar);
    }

    private NavigationResult GoToTick(int p, int b, int tick, bool byBar)
    {
        var bar = _doc.Parts[p].Bars[b];
        int at = bar.Events.FindIndex(x => x.Tick == tick && !IsTieContinuationOrHeld(x));
        if (at >= 0)
        {
            var r = Go(p, b, at, byBar);
            TickInBar = tick;
            return r;
        }
        // Something still sounding at this tick: announce it as held.
        int covering = bar.Events.FindLastIndex(x => x.Tick <= tick);
        PartIndex = p;
        BarIndex = b;
        TickInBar = tick;
        if (covering < 0)
        {
            // A tie continuation at the bar start covers the tick.
            return Go(p, b, 0, byBar);
        }
        var src = bar.Events[covering];
        EventIndex = covering;
        var pos = MusicXmlTalkingScoreBuilder.Position(tick, MusicXmlTalkingScoreBuilder.TicksPerQuarter, bar.Time);
        if (src.Kind is EventKind.Note or EventKind.Chord || IsTieContinuation(src))
        {
            var (headBar, head) = TieHead(p, b, covering);
            var headPos = head.Pos ?? new TsPos(1);
            _synthetic = new TsEvent
            {
                Kind = EventKind.Held,
                Pos = pos,
                Tick = tick,
                Written = src.Written,
                Concert = src.Concert,
                HeldFrom = new TsHeldFrom(_doc.Parts[p].Bars[headBar].Number, headPos.Beat, headPos.Num, headPos.Den),
            };
        }
        else
        {
            // A rest still running at this beat: say the rest from this position.
            _synthetic = new TsEvent { Kind = src.Kind, Pos = pos, Tick = tick, Type = src.Type, Dots = src.Dots, Bars = src.Bars };
        }
        Text = Announce(_doc.Parts[p], b, _synthetic ?? src, byBar);
        Moved?.Invoke(this, Text);
        return new NavigationResult(Text, true);
    }

    private (int Bar, TsEvent Head) TieHead(int p, int b, int e)
    {
        var part = _doc.Parts[p];
        var ev = part.Bars[b].Events[e];
        while (IsTieContinuation(ev))
        {
            // Walk back to the previous note of the same pitch.
            if (--e < 0)
            {
                if (--b < 0) break;
                e = part.Bars[b].Events.Count - 1;
                if (e < 0) break;
            }
            ev = part.Bars[b].Events[e];
        }
        return (Math.Max(b, 0), ev);
    }

    private string Announce(TsPart part, int barIndex, TsEvent ev, bool byBar, bool updateContext = true)
    {
        var text = Announcer.Announce(ToAnnouncePart(part), ToAnnounceBar(barIndex, byBar), ev, _context, Settings, byBar);
        if (updateContext) _context = new AnnounceContext(part.Name, part.Bars[barIndex].Number, Settings.PitchMode);
        return text;
    }

    private static AnnouncePart ToAnnouncePart(TsPart p) => new(p.Name, p.NameNb, p.Instrument, p.InstrumentNb, p.Transpose);

    private AnnounceBar ToAnnounceBar(int barIndex, bool byBar)
    {
        var bars = Part.Bars;
        var bar = bars[barIndex];
        var prev = barIndex > 0 ? bars[barIndex - 1] : null;
        var region = _doc.RegionAt(bar.Number);
        var prevRegion = _context.Bar is { } cb ? _doc.RegionAt(cb) : null;
        bool entering = region is not null && !ReferenceEquals(region, prevRegion);
        bool aTempo = region is null && prevRegion is not null;
        double? tempo = bar.TempoBpm;
        if (aTempo) tempo ??= LastTempoBefore(barIndex);
        else if (tempo is not null && prev is not null && EffectiveTempo(barIndex - 1) == tempo) tempo = null;
        if (barIndex == 0 && !byBar) tempo = null;

        return new AnnounceBar(
            Number: bar.Number,
            KeyFifths: bar.KeyFifths,
            KeyChanged: prev is not null && prev.KeyFifths != bar.KeyFifths,
            TimeChanged: prev is not null && prev.Time != bar.Time ? bar.Time : null,
            TempoMarked: tempo,
            Rehearsal: bar.Rehearsal,
            FreeRegion: region,
            EnteringRegion: entering,
            ATempo: aTempo && tempo is not null,
            TotalBars: _doc.TotalBars);
    }

    private double? EffectiveTempo(int barIndex)
    {
        for (int i = barIndex; i >= 0; i--)
            if (Part.Bars[i].TempoBpm is { } t) return t;
        return null;
    }

    private double? LastTempoBefore(int barIndex)
    {
        for (int i = barIndex - 1; i >= 0; i--)
            if (Part.Bars[i].TempoBpm is { } t && _doc.RegionAt(Part.Bars[i].Number) is null) return t;
        return null;
    }

    private static bool IsTieContinuation(TsEvent ev) => ev.Tie is { Stop: true };
    private static bool IsTieContinuationOrHeld(TsEvent ev) => IsTieContinuation(ev) || ev.Kind == EventKind.Held;
    private static bool IsRestBar(TsBar bar) => bar.Events.Count == 1 && bar.Events[0].Kind == EventKind.BarRest;

    internal static int BeatTicks(TsTime time)
    {
        bool compound = time.BeatType == 8 && time.Beats % 3 == 0 && time.Beats > 3;
        return MusicXmlTalkingScoreBuilder.TicksPerQuarter * 4 / time.BeatType * (compound ? 3 : 1);
    }

    private static int BarBeats(TsBar bar)
    {
        bool compound = bar.Time.BeatType == 8 && bar.Time.Beats % 3 == 0 && bar.Time.Beats > 3;
        return compound ? bar.Time.Beats / 3 : bar.Time.Beats;
    }
}
