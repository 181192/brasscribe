using System.Collections.ObjectModel;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

public sealed record ScorePartItem(int Index, string Name, string? Instrument, int UncertainCount);

/// <summary>The source label's icons (Segoe Fluent Icons, as BcIconRecordMic and BcIconParts): the record mic for the recording, the parts for arranged.</summary>
public static class SourceGlyphs
{
    public const string Recording = "\uE720";
    public const string Arranged = "\uEA37";
}

/// <summary>
/// The review and practice score: parts, written/concert pitch, zoom, the talking-score cursor and
/// every score command from the keyboard map. The notation view and its automation peer read
/// <see cref="Announcement"/> and <see cref="CurrentBar"/>; they never build strings themselves.
/// </summary>
public sealed partial class ScoreViewModel : ObservableObject
{
    private readonly ICoreBridge _core;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private ScoreNavigator? _nav;

    public ScoreViewModel(ICoreBridge core, PlayerViewModel player, IAnnouncer announcer, IStrings strings, IOriginalPlayer? original = null)
    {
        _core = core;
        Player = player;
        _announcer = announcer;
        _s = strings;
        Original = original;
        player.BarOnceEnded += (_, _) => EndListening();
        if (original is not null) original.RangeEnded += (_, _) => EndListening();
        // The native core humanizes playback; the managed fallback plays the score's exact timing.
        if (core.IsNative && player.Player is Playback.AlphaTabScorePlayer alphaTab) alphaTab.Humanizer ??= core.Humanize;
        Stand = new MusicStandViewModel(this, announcer, strings);
    }

    public PlayerViewModel Player { get; }

    /// <summary>The music stand: the score alone, in pages (design/music-stand.md).</summary>
    public MusicStandViewModel Stand { get; }

    private bool _quietPart;

    /// <summary>
    /// Shows one part (or, with -1, every part) without the part view's side effects: no announcement
    /// and no change to whose part is muted. The music stand speaks for itself and leaves the mix alone.
    /// </summary>
    public void ShowPartQuietly(int index)
    {
        _quietPart = true;
        try { SelectedPartIndex = index; }
        finally { _quietPart = false; }
    }

    /// <summary>Set when the band sounds are not installed: one line above the player says so.</summary>
    public bool BandSoundsMissing => Player.Player is AlphaTabScorePlayer { SoundsMissingFrom: not null };
    public string BandSoundsMissingText => BandSoundsMissing ? _s["Player_SoundsMissing"] : "";
    /// <summary>Where the band sounds were expected, for the band's tech person.</summary>
    public string BandSoundsMissingDetails =>
        Player.Player is AlphaTabScorePlayer { SoundsMissingFrom: { } path } ? _s.Format("Player_SoundsMissing_Details", path) : "";
    public string TechDetailsHeading => _s["Error_DetailsHeading"];
    public IOriginalPlayer? Original { get; }
    public TalkingScoreDocument? Document { get; private set; }
    public Composition? Composition { get; private set; }
    public string? MusicXml { get; private set; }
    public Action<string, string?>? PersistEditedScore { get; set; }

    /// <summary>Confidence and what each transcriber heard at the uncertain notes; null for opened files.</summary>
    public Engine.Evidence? Evidence { get; set; }

    public Action<Engine.Evidence>? PersistEvidence { get; set; }
    public ScoreNavigator? Navigator => _nav;

    public ObservableCollection<ScorePartItem> Parts { get; } = [];

    /// <summary>Raised when the cursor moves, so the view can scroll, highlight and raise UIA events.</summary>
    public event EventHandler<string>? CursorMoved;

    [ObservableProperty] public partial string Title { get; set; } = "";
    [ObservableProperty] public partial bool IsLoaded { get; set; }

    /// <summary>-1 shows the full score; otherwise the index of the single part shown.</summary>
    [ObservableProperty] public partial int SelectedPartIndex { get; set; } = -1;

    [ObservableProperty] public partial bool ConcertPitch { get; set; }
    [ObservableProperty] public partial double ZoomPercent { get; set; } = 100;
    [ObservableProperty] public partial bool ShowTalkingScore { get; set; }
    [ObservableProperty] public partial string Announcement { get; set; } = "";
    [ObservableProperty] public partial int CurrentBar { get; set; } = 1;
    [ObservableProperty] public partial int CurrentPartIndex { get; set; }
    [ObservableProperty] public partial int UncertainLeft { get; set; }
    [ObservableProperty] public partial string UncertainText { get; set; } = "";
    [ObservableProperty] public partial string Language { get; set; } = "en";
    [ObservableProperty] public partial Verbosity Verbosity { get; set; } = Verbosity.Standard;
    [ObservableProperty] public partial bool SingleKeyShortcuts { get; set; } = true;
    [ObservableProperty] public partial bool HasFreeTime { get; set; }

    /// <summary>The original is a video: the score screen shows it and offers picture-in-picture.</summary>
    [ObservableProperty] public partial bool HasVideo { get; set; }

    /// <summary>What the transport plays: the arranged score or the original recording.</summary>
    [ObservableProperty] public partial ListeningSource ListeningTo { get; set; } = ListeningSource.Score;

    /// <summary>Score ↔ recording time, when the score came with a Composition.</summary>
    public ScoreTimeMap? TimeMap => Composition is { } c ? new ScoreTimeMap(c) : null;

    public bool CanSwitchSource => Original is { HasMedia: true } && Composition is not null;

    /// <summary>
    /// Switches between the score and the original at the same musical position; playback carries on
    /// in the other source if it was playing.
    /// </summary>
    [RelayCommand]
    public void SwitchSource()
    {
        if (Original is not { HasMedia: true } original || TimeMap is not { } map)
        {
            _announcer.Announce(_s["Score_NoOriginal"]);
            return;
        }
        var player = Player.Player;
        if (ListeningTo == ListeningSource.Score)
        {
            bool playing = player.State == PlaybackState.Playing;
            double seconds = map.SecondsAtTick(player.Position.Tick);
            player.Pause();
            original.IsMuted = false;
            original.Rate = 1;
            original.Position = TimeSpan.FromSeconds(seconds);
            if (playing) original.Play();
            ListeningTo = ListeningSource.Original;
            _announcer.Announce(_s.Format("Score_SwitchedToOriginal", player.Position.BarIndex + 1));
        }
        else
        {
            bool playing = original.IsPlaying;
            double tick = map.TickAtSeconds(original.Position.TotalSeconds);
            original.Pause();
            player.SeekToTick(tick);
            if (playing) player.Play();
            ListeningTo = ListeningSource.Score;
            _announcer.Announce(_s["Score_SwitchedToScore"]);
        }
    }

    /// <summary>Lines of the talking-score view for the current part, one per event.</summary>
    public ObservableCollection<string> TalkingLines { get; } = [];

    /// <summary>Index into <see cref="TalkingLines"/> of the cursor position (the text selection).</summary>
    [ObservableProperty] public partial int CurrentLineIndex { get; set; }

    private readonly List<(int Bar, int Event)> _linePositions = [];

    public void Load(string musicXml, Composition? composition)
    {
        MusicXml = musicXml;
        Composition = composition;
        Document = _core.BuildTalkingScore(musicXml, composition);
        Review.ReviewGroups.Attach(Document, composition);
        Title = Document.Title;
        HasFreeTime = Document.FreeRegions.Count > 0;
        _nav = new ScoreNavigator(Document, Settings());
        Parts.Clear();
        for (int i = 0; i < Document.Parts.Count; i++)
        {
            var p = Document.Parts[i];
            int uncertain = p.Bars.Sum(b => b.Events.Count(e => e.IsUncertain && e.Tie is not { Stop: true }));
            Parts.Add(new ScorePartItem(i, Language == "nb" ? p.NameNb ?? p.Name : p.Name, Language == "nb" ? p.InstrumentNb ?? p.Instrument : p.Instrument, uncertain));
        }
        if (Player.Player is Playback.AlphaTabScorePlayer alphaTabPlayer)
            alphaTabPlayer.PerformanceJson = composition is null ? null : CompositionJson.Serialize(composition);
        Player.PartLabel = PartLabel;
        Player.Load(System.Text.Encoding.UTF8.GetBytes(musicXml));
        _sources = SourcesOf(composition);
        foreach (var m in Player.Parts) ShowSource(m);
        ApplyYourPart();
        IsLoaded = true;
        HasVideo = Original?.HasVideo == true;
        ListeningTo = ListeningSource.Score;
        UpdateUncertain();
        Sync(_nav.Text, announce: false);
        RebuildTalkingLines();
    }

    /// <summary>Arranges the score again from a changed Composition (the native core); null when that can't be done here.</summary>
    public Func<Composition, string?>? Rearrange { get; set; }

    /// <summary>
    /// A kept review group: every printed note of it in this part loses its mark and its Composition
    /// notes get confidence 1, so the group stays kept when the score is loaded or arranged again.
    /// </summary>
    public void KeepGroup(int partIndex, TsEvent lead)
    {
        if (Document is null || lead.ReviewGroup < 0 || partIndex < 0 || partIndex >= Document.Parts.Count) return;
        foreach (var (_, ev) in Review.ReviewGroups.Members(Document.Parts[partIndex], lead.ReviewGroup)) ev.Checked = true;
        if (Composition is { Review: { } spans } composition && lead.ReviewGroup < spans.Count)
        {
            var span = spans[lead.ReviewGroup];
            foreach (var n in Review.ReviewGroups.NotesOf(composition, span)) n.Confidence = 1.0;
            if (MusicXml is not null) PersistEditedScore?.Invoke(MusicXml, CompositionJson.Serialize(composition));
        }
        UpdateUncertain();
    }

    /// <summary>A kept note: its Composition note gets confidence 1, so it stays kept when the score is arranged again.</summary>
    public void KeepInComposition(TsEvent ev)
    {
        if (Composition is not { } composition || ev.CompositionVoiceId is not { } voiceId || ev.CompositionNoteStart is not { } start) return;
        var note = composition.Voices.FirstOrDefault(v => v.Id == voiceId)?.Notes.FirstOrDefault(n => n.Start == start);
        if (note is null || note.Confidence >= 1.0) return;
        note.Confidence = 1.0;
        if (MusicXml is not null) PersistEditedScore?.Invoke(MusicXml, CompositionJson.Serialize(composition));
    }

    public bool CorrectPitch(int partIndex, int barIndex, int eventIndex, int semitones)
    {
        if (MusicXml is null || Document is null || partIndex < 0 || partIndex >= Document.Parts.Count) return false;
        var part = Document.Parts[partIndex];
        if (barIndex < 0 || barIndex >= part.Bars.Count || eventIndex < 0 || eventIndex >= part.Bars[barIndex].Events.Count) return false;
        var ev = part.Bars[barIndex].Events[eventIndex];
        if (ev.Written is not { } written || ev.MusicXmlNoteIndex < 0) return false;
        int midi = Announcer.Midi(written) + semitones;
        if (midi is < 0 or > 127) return false;
        string? compositionJson = null;
        if (Composition is { } composition && ev.CompositionVoiceId is { } voiceId && ev.CompositionNoteStart is { } noteStart)
        {
            var sourceNote = composition.Voices.FirstOrDefault(v => v.Id == voiceId)?.Notes.FirstOrDefault(n => n.Start == noteStart);
            if (sourceNote is not null)
            {
                int old = sourceNote.Pitch;
                sourceNote.Pitch = Math.Clamp(sourceNote.Pitch + semitones, 0, 127);
                compositionJson = CompositionJson.Serialize(composition);
                // The evidence follows the note: the musician's pitch is now the one each transcriber is compared to.
                if (Evidence is { } evidence && evidence.Notes.Any(n => n.Voice == voiceId && n.Start == noteStart && n.Pitch == old))
                {
                    int now = sourceNote.Pitch;
                    Evidence = evidence with
                    {
                        Notes = evidence.Notes.Select(n => n.Voice == voiceId && n.Start == noteStart && n.Pitch == old
                            ? n with { Pitch = now, Models = n.Models.Select(m => m with { Agrees = m.Pitch == now }).ToList() }
                            : n).ToList(),
                    };
                    PersistEvidence?.Invoke(Evidence);
                }
            }
        }
        // With the changed Composition the whole score is arranged again (other parts that double the
        // line follow it); without an arranger here, only this printed note changes.
        string edited = compositionJson is not null && Composition is { } changed && Rearrange?.Invoke(changed) is { } arranged
            ? arranged
            : MusicXmlNoteEditor.ReplacePitch(MusicXml, part.Id, ev.MusicXmlNoteIndex, midi, part.Bars[barIndex].KeyFifths);
        Player.Player.Pause();
        PersistEditedScore?.Invoke(edited, compositionJson);
        Load(edited, Composition);
        return true;
    }

    private TalkingScoreSettings Settings() => new(Language, ConcertPitch ? PitchMode.Concert : PitchMode.Written, Verbosity);

    partial void OnLanguageChanged(string value) => ApplySettings();
    partial void OnVerbosityChanged(Verbosity value) => ApplySettings();

    partial void OnConcertPitchChanged(bool value)
    {
        if (_nav is null) return;
        string text = _nav.SetPitchMode(value ? PitchMode.Concert : PitchMode.Written);
        _announcer.Announce(text);
        RebuildTalkingLines();
    }

    /// <summary>The original video is shown beside the score (View ▾ Show video).</summary>
    [ObservableProperty] public partial bool ShowVideo { get; set; } = true;

    /// <summary>"As written for B♭" for the chosen part's instrument, "As written" for all parts or a part in C.</summary>
    public string WrittenLabel
    {
        get
        {
            if (Document is null || SelectedPartIndex < 0 || SelectedPartIndex >= Document.Parts.Count) return _s["Score_AsWritten"];
            int pc = ((Document.Parts[SelectedPartIndex].Transpose.Chromatic % 12) + 12) % 12;
            string? key = pc switch { 10 => "B♭", 3 => "E♭", 5 => "F", 9 => "A", 2 => "D", 7 => "G", _ => null };
            return key is null ? _s["Score_AsWritten"] : _s.Format("Score_AsWrittenFor", key);
        }
    }

    /// <summary>"SOLO CORNET IN B♭", the part view's page header.</summary>
    public string PartHeader => Document is null || SelectedPartIndex < 0 || SelectedPartIndex >= Document.Parts.Count ? ""
        : ((Language == "nb" ? Document.Parts[SelectedPartIndex].InstrumentNb : null) ?? Document.Parts[SelectedPartIndex].Instrument
           ?? Document.Parts[SelectedPartIndex].Name).ToUpperInvariant();

    /// <summary>
    /// The player's own part in the score (the one "Mute my part" silences), or -1 when no part is theirs
    /// ("I conduct or listen", or a lineup without their seat).
    /// </summary>
    public int MyPartIndex
    {
        get
        {
            if (Document is null || Document.Parts.Count == 0) return -1;
            if (Player.PlayAlongPart is { } mine && Document.Parts.FindIndex(p => p.Name == mine.Name) is var i and >= 0) return i;
            return -1;
        }
    }

    /// <summary>A part is the player's: Mute my part, Only my part and "(you)" are offered.</summary>
    public bool HasMyPart => MyPartIndex >= 0;

    /// <summary>The player's part by its shown name ("Eufonium"), empty when none.</summary>
    public string MyPartLabel => MyPartIndex >= 0 ? PartLabelOf(Document!.Parts[MyPartIndex].Name) : "";

    /// <summary>Works out whose part is whose for this score (the seat, the lineup, the part chosen for it); null keeps the first Solo part.</summary>
    public Func<IReadOnlyList<Seats.ScorePart>, Seats.YourPartResult>? YourPartResolver { get; set; }

    /// <summary>The words for a lineup that lacks the player's seat; null when there is nothing to say.</summary>
    public Func<IReadOnlyList<Seats.ScorePart>, Seats.YourPartResult, string?>? YourPartNoticeText { get; set; }

    /// <summary>"Make this my part" saves the part (by name) with the score.</summary>
    public Action<string>? PersistMyPart { get; set; }

    /// <summary>A part's name in the UI language, from the core's one table.</summary>
    public Func<string, string>? PartLabel { get; set; }

    /// <summary>"This small band has no 1st Baritone. Your part here is Euphonium, …"; empty when the seat has its own part.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasYourPartNotice))]
    public partial string YourPartNotice { get; set; } = "";

    public bool HasYourPartNotice => YourPartNotice.Length > 0;

    private string PartLabelOf(string name) => PartLabel?.Invoke(name) ?? name;

    /// <summary>The parts of the shown score as "your part" is looked up in them.</summary>
    public IReadOnlyList<Seats.ScorePart> ScoreParts =>
        Document?.Parts.Select(p => new Seats.ScorePart(p.Name, p.Transpose.Chromatic, p.Percussion)).ToList() ?? [];

    /// <summary>
    /// Works out the player's part again (the seat changed in Settings). Only the highlight, the mute target and
    /// the order of the notes to check change; the score is not arranged again.
    /// </summary>
    public void RefreshYourPart()
    {
        if (Document is null) return;
        ApplyYourPart();
    }

    private void ApplyYourPart()
    {
        var parts = ScoreParts;
        var result = YourPartResolver?.Invoke(parts) ?? new Seats.YourPartResult(parts.Count == 0 ? -1 : Seats.YourPart.Legacy(parts));
        SetMine(result.Index >= 0 && result.Index < parts.Count ? parts[result.Index].Name : null);
        YourPartNotice = YourPartNoticeText?.Invoke(parts, result) ?? "";
        // Said once, politely, when the score opens (WCAG 4.1.3).
        if (YourPartNotice.Length > 0) _announcer.Announce(YourPartNotice);
    }

    /// <summary>"Make this my part": only the highlight, the mute target, the review order and the share scope change, at once.</summary>
    public void MakeMine(int index)
    {
        if (Document is null || index < 0 || index >= Document.Parts.Count) return;
        string name = Document.Parts[index].Name;
        SetMine(name);
        YourPartNotice = "";
        PersistMyPart?.Invoke(name);
        _announcer.Announce(_s.Format("Score_MadeMine", PartLabelOf(name)));
    }

    private void SetMine(string? name)
    {
        // Mute my part follows the part: the old one sounds again, the new one is muted if it was on.
        bool muted = Player.MuteMyPart;
        if (muted) Player.MuteMyPart = false;
        Player.PlayAlongPart = name is null ? null : Player.Parts.FirstOrDefault(m => m.Name == name);
        if (muted && Player.PlayAlongPart is not null) Player.MuteMyPart = true;
        OnPropertyChanged(nameof(MyPartIndex));
        OnPropertyChanged(nameof(HasMyPart));
        OnPropertyChanged(nameof(MyPartLabel));
        OnPropertyChanged(nameof(MyPartSourceIsArranged));
        OnPropertyChanged(nameof(CanMakeShownMine));
        Stand.YourPartChanged();
    }

    private IReadOnlyDictionary<string, string> _sources = new Dictionary<string, string>();

    /// <summary>Where a part came from (your-recording, recording, arranged), by its own name; null when not known.</summary>
    public string? SourceOf(string partName) => _sources.TryGetValue(partName, out var source) ? source : null;

    /// <summary>The player's part was arranged from the harmony: there are no notes of theirs to check.</summary>
    public bool MyPartSourceIsArranged => MyPartIndex >= 0 && SourceOf(Document!.Parts[MyPartIndex].Name) == PartSource.Arranged;

    /// <summary>The source label's words ("From the recording"); empty when not known.</summary>
    public string SourceLabelOf(string partName) => SourceOf(partName) switch
    {
        PartSource.YourRecording => _s["Source_YourRecording"],
        PartSource.Recording => _s["Source_Recording"],
        PartSource.Arranged => _s["Source_Arranged"],
        _ => "",
    };

    /// <summary>The one sentence a source label opens.</summary>
    public string SourceExplanationOf(string partName) => SourceOf(partName) switch
    {
        PartSource.YourRecording => _s["Source_Explain_YourRecording"],
        PartSource.Recording => _s["Source_Explain_Recording"],
        PartSource.Arranged => _s["Source_Explain_Arranged"],
        _ => "",
    };

    private IReadOnlyDictionary<string, string> SourcesOf(Composition? composition)
    {
        if (composition is null || !_core.IsNative) return new Dictionary<string, string>();
        try { return _core.PartSources(CompositionJson.Serialize(composition)); }
        catch (CoreBridgeException) { return new Dictionary<string, string>(); }
    }

    private void ShowSource(MixerPartViewModel m)
    {
        var source = SourceOf(m.Name);
        m.SourceLabel = SourceLabelOf(m.Name);
        m.SourceExplanation = SourceExplanationOf(m.Name);
        m.SourceGlyph = source switch
        {
            null => "",
            PartSource.Arranged => SourceGlyphs.Arranged,
            _ => SourceGlyphs.Recording,
        };
    }

    /// <summary>The part view: one part chosen, laid out as a page, with the player's own part muted.</summary>
    public bool IsPartView => SelectedPartIndex >= 0;

    /// <summary>The shown part's source label ("Arranged from the band's harmony"), for the part view's header; empty when unknown.</summary>
    public string ShownSourceLabel => ShownPartName is { } n ? SourceLabelOf(n) : "";
    public string ShownSourceExplanation => ShownPartName is { } n ? SourceExplanationOf(n) : "";
    public string ShownSourceGlyph => ShownPartName is { } n ? SourceOf(n) switch { null => "", PartSource.Arranged => SourceGlyphs.Arranged, _ => SourceGlyphs.Recording } : "";
    public bool HasShownSource => ShownSourceLabel.Length > 0;

    /// <summary>"Make this my part" is offered in the part view of a part that is not the player's.</summary>
    public bool CanMakeShownMine => IsPartView && SelectedPartIndex != MyPartIndex;

    private string? ShownPartName => Document is { } d && SelectedPartIndex >= 0 && SelectedPartIndex < d.Parts.Count ? d.Parts[SelectedPartIndex].Name : null;

    partial void OnSelectedPartIndexChanged(int value)
    {
        OnPropertyChanged(nameof(IsPartView));
        OnPropertyChanged(nameof(ShownSourceLabel));
        OnPropertyChanged(nameof(ShownSourceExplanation));
        OnPropertyChanged(nameof(ShownSourceGlyph));
        OnPropertyChanged(nameof(HasShownSource));
        OnPropertyChanged(nameof(CanMakeShownMine));
        OnPropertyChanged(nameof(WrittenLabel));
        OnPropertyChanged(nameof(PartHeader));
        if (_nav is null || value < 0) return;
        // Your own part on its page is muted, to play along. Another part is only shown: your part stays yours.
        if (!_quietPart && value == MyPartIndex && !Player.MuteMyPart) Player.MuteMyPart = true;
        _nav.GoToPart(value);
        var part = Document!.Parts[value];
        string name = Language == "nb" ? part.NameNb ?? part.Name : part.Name;
        string mode = _nav.SetPitchMode(ConcertPitch ? PitchMode.Concert : PitchMode.Written);
        if (!_quietPart) _announcer.Announce(_s.Format("Score_PartShown", name) + " " + mode);
        Sync(_nav.Text, announce: false);
        RebuildTalkingLines();
    }

    partial void OnZoomPercentChanged(double value)
    {
        double snapped = Math.Clamp(Math.Round(value / 10) * 10, 50, 400);
        if (Math.Abs(snapped - value) > 1e-9) ZoomPercent = snapped;
    }

    private void ApplySettings()
    {
        if (_nav is null) return;
        _nav.Settings = Settings();
        RebuildTalkingLines();
    }

    /// <summary>Runs a score command; returns true when it was handled.</summary>
    public bool Execute(ScoreCommand command)
    {
        if (_nav is null) return false;
        if (ExecuteStand(command)) return true;
        NavigationResult? r = command switch
        {
            ScoreCommand.NextNote => _nav.NextNote(),
            ScoreCommand.PreviousNote => _nav.PreviousNote(),
            ScoreCommand.NextBeat => _nav.NextBeat(),
            ScoreCommand.PreviousBeat => _nav.PreviousBeat(),
            ScoreCommand.NextBar => _nav.NextBar(),
            ScoreCommand.PreviousBar => _nav.PreviousBar(),
            ScoreCommand.NextPart => _nav.NextPart(),
            ScoreCommand.PreviousPart => _nav.PreviousPart(),
            ScoreCommand.FirstBar => _nav.FirstBar(),
            ScoreCommand.LastBar => _nav.LastBar(),
            ScoreCommand.NextUncertain => _nav.NextUncertain(),
            ScoreCommand.PreviousUncertain => _nav.PreviousUncertain(),
            _ => null,
        };
        if (r is not null)
        {
            if (r.Moved) Sync(r.Text, announce: false);
            else _announcer.Announce(r.Text);
            return true;
        }

        int bar = _nav.Bar.Number;
        switch (command)
        {
            case ScoreCommand.MarkChecked: MarkChecked(); break;
            case ScoreCommand.ReadBar: _announcer.Announce(_nav.ReadBar()); break;
            case ScoreCommand.WhereAmI: _announcer.Announce(_nav.WhereAmI()); break;
            case ScoreCommand.PlayBar: ListenToBar(); break;
            case ScoreCommand.PlayFrom: Player.PlayFrom(bar); break;
            case ScoreCommand.PlayPause:
                if (ListeningTo == ListeningSource.Original && Original is { } o)
                {
                    if (o.IsPlaying) o.Pause(); else o.Play();
                }
                else Player.PlayPauseCommand.Execute(null);
                break;
            case ScoreCommand.SwitchSource: SwitchSource(); break;
            case ScoreCommand.LoopStartHere: Player.SetLoopStartAt(bar); break;
            case ScoreCommand.LoopEndHere: Player.SetLoopEndAt(bar); break;
            case ScoreCommand.ToggleLoop: Player.ToggleLoopCommand.Execute(null); break;
            case ScoreCommand.Slower: Player.SlowerBy5Command.Execute(null); AnnounceSpeed(); break;
            case ScoreCommand.Faster: Player.FasterBy5Command.Execute(null); AnnounceSpeed(); break;
            case ScoreCommand.ResetSpeed: Player.ResetSpeedCommand.Execute(null); AnnounceSpeed(); break;
            case ScoreCommand.ToggleMute: Player.ToggleMute(_nav.PartIndex); break;
            case ScoreCommand.ToggleSolo: Player.ToggleSolo(_nav.PartIndex); break;
            case ScoreCommand.ToggleCountIn:
                Player.CountIn = !Player.CountIn;
                _announcer.Announce(_s[Player.CountIn ? "Player_CountInOn" : "Player_CountInOff"]);
                break;
            case ScoreCommand.ToggleMetronome:
                Player.Metronome = !Player.Metronome;
                _announcer.Announce(_s[Player.Metronome ? "Player_MetronomeOn" : "Player_MetronomeOff"]);
                break;
            case ScoreCommand.ZoomIn: ZoomPercent += 10; _announcer.Announce(_s.Format("Score_Zoom", ZoomPercent)); break;
            case ScoreCommand.ZoomOut: ZoomPercent -= 10; _announcer.Announce(_s.Format("Score_Zoom", ZoomPercent)); break;
            case ScoreCommand.ZoomReset: ZoomPercent = 100; _announcer.Announce(_s.Format("Score_Zoom", ZoomPercent)); break;
            default: return false;
        }
        return true;
    }

    /// <summary>The stand's own commands; inside the stand, bar moves go through the player so one bar drives the pages.</summary>
    private bool ExecuteStand(ScoreCommand command)
    {
        switch (command)
        {
            case ScoreCommand.ToggleStand: Stand.Toggle(); return true;
            case ScoreCommand.LeaveStand: Stand.Leave(); return true;
        }
        if (!Stand.IsOpen) return command is ScoreCommand.NextPage or ScoreCommand.PreviousPage or ScoreCommand.FirstPage or ScoreCommand.LastPage;
        switch (command)
        {
            case ScoreCommand.NextPage: Stand.NextPage(); return true;
            case ScoreCommand.PreviousPage: Stand.PreviousPage(); return true;
            case ScoreCommand.FirstPage: Stand.FirstPage(); return true;
            case ScoreCommand.LastPage: Stand.LastPage(); return true;
            case ScoreCommand.NextBar: Player.NextBarCommand.Execute(null); return true;
            case ScoreCommand.PreviousBar: Player.PreviousBarCommand.Execute(null); return true;
            default: return false;
        }
    }

    [RelayCommand]
    public void GoToBar(int number)
    {
        if (_nav is null) return;
        var r = _nav.GoToBar(number);
        if (r.Moved) Sync(r.Text, announce: true);
        else _announcer.Announce(r.Text, AnnouncementKind.Important);
    }

    /// <summary>Puts the talking-score cursor on one event, without announcing it (the review screen speaks for itself).</summary>
    public void FocusEvent(int part, int barIndex, int eventIndex)
    {
        if (_nav is null) return;
        var r = _nav.GoToEvent(part, barIndex, eventIndex);
        if (r.Moved) Sync(r.Text, announce: false);
    }

    /// <summary>Marks the note under the cursor as checked without announcing (the caller does).</summary>
    public int KeepCurrent()
    {
        if (_nav is null) return 0;
        int left = _nav.MarkChecked();
        UpdateUncertain();
        Announcement = _nav.Text;
        return left;
    }

    [RelayCommand]
    private void MarkChecked()
    {
        if (_nav is null) return;
        int left = _nav.MarkChecked();
        UpdateUncertain();
        _announcer.Announce(_s.Format("Score_Checked", left));
        Announcement = _nav.Text;
    }

    /// <summary>A bar from "Listen to this bar" is playing; the button says "Stop" meanwhile.</summary>
    [ObservableProperty] public partial bool IsListeningToBar { get; private set; }

    private int _listeningBar;
    private bool _listeningOriginal;

    /// <summary>
    /// "Listen to this bar", and "Stop" while it plays: the bar once, from the original recording when it
    /// is loaded and timed, else from the score. It goes back to "Listen" when the bar ends.
    /// </summary>
    [RelayCommand]
    private void ListenToBar()
    {
        if (IsListeningToBar)
        {
            StopListening();
            return;
        }
        if (_nav is null) return;
        int bar = _nav.Bar.Number;
        if (Original is { HasMedia: true } && BarSeconds(_nav.PartIndex, _nav.BarIndex) is { } span)
        {
            Original.IsMuted = false; // the video follower may have left it muted
            Original.PlayRange(TimeSpan.FromSeconds(span.Start), TimeSpan.FromSeconds(span.End), loop: false);
            _listeningOriginal = true;
            _announcer.Announce(_s.Format("Score_ListeningOriginal", bar));
        }
        else
        {
            if (!Player.Player.IsReady)
            {
                _announcer.Announce(_s["Player_NotReady"], AnnouncementKind.Important);
                return;
            }
            Player.PlayBarOnce(bar);
            _listeningOriginal = false;
            _announcer.Announce(_s.Format("Score_ListeningScore", bar));
        }
        _listeningBar = bar;
        IsListeningToBar = true;
    }

    /// <summary>Stops "Listen to this bar" (Stop, another place, leaving the screen). Quiet when the move itself is announced.</summary>
    public void StopListening(bool announce = true)
    {
        if (!IsListeningToBar) return;
        if (_listeningOriginal) Original?.Stop();
        else Player.StopBarOnce();
        IsListeningToBar = false;
        if (announce) _announcer.Announce(_s["Score_ListenStopped"]);
    }

    /// <summary>The bar played to its end: back to "Listen".</summary>
    private void EndListening()
    {
        if (!IsListeningToBar) return;
        IsListeningToBar = false;
        _announcer.Announce(_s.Format("Score_ListenEnded", _listeningBar));
    }

    /// <summary>Shows the "Stop" state without playing (screenshots of the listening state).</summary>
    internal void PreviewListening() => IsListeningToBar = true;

    /// <summary>Recording time of a bar from the first timed events of it and the next bar.</summary>
    public (double Start, double End)? BarSeconds(int partIndex, int barIndex)
    {
        if (Document is null) return null;
        var bars = Document.Parts[partIndex].Bars;
        double? Start(int b)
        {
            for (int p = 0; p < Document.Parts.Count; p++)
            {
                var pb = Document.Parts[p].Bars;
                if (b < pb.Count && pb[b].Events.FirstOrDefault(e => e.TimeS is not null && e.Tick == 0) is { } ev) return ev.TimeS;
            }
            return null;
        }
        if (Start(barIndex) is not { } s) return null;
        double e = barIndex + 1 < bars.Count && Start(barIndex + 1) is { } next ? next : s + 4;
        return (s, e);
    }

    private void AnnounceSpeed() => _announcer.Announce(_s.Format("Player_Speed", Player.SpeedPercent));

    private void Sync(string text, bool announce)
    {
        // Another bar: "Listen to this bar" was about the old one.
        if (IsListeningToBar && _nav!.Bar.Number != _listeningBar) StopListening(announce: false);
        Announcement = text;
        CurrentBar = _nav!.Bar.Number;
        CurrentPartIndex = _nav.PartIndex;
        CurrentLineIndex = LineIndexOf(_nav.BarIndex, _nav.EventIndex);
        CursorMoved?.Invoke(this, text);
        if (announce) _announcer.Announce(text);
    }

    /// <summary>Recounts the notes still marked ? (after the review screen kept some).</summary>
    public void RefreshUncertain() => UpdateUncertain();

    private void UpdateUncertain()
    {
        UncertainLeft = _nav?.UncertainCount ?? 0;
        UncertainText = _s.Format(UncertainLeft == 1 ? "Score_UncertainLeftOne" : "Score_UncertainLeft", UncertainLeft);
    }

    private void RebuildTalkingLines()
    {
        TalkingLines.Clear();
        _linePositions.Clear();
        if (Document is null || _nav is null) return;
        int part = SelectedPartIndex >= 0 ? SelectedPartIndex : _nav.PartIndex;
        var walker = new ScoreNavigator(Document, _nav.Settings);
        walker.GoToPart(part);
        walker.FirstBar();
        TalkingLines.Add(walker.Text);
        _linePositions.Add((walker.BarIndex, walker.EventIndex));
        while (walker.NextNote() is { Moved: true } r)
        {
            TalkingLines.Add(r.Text);
            _linePositions.Add((walker.BarIndex, walker.EventIndex));
        }
        CurrentLineIndex = LineIndexOf(_nav.BarIndex, _nav.EventIndex);
    }

    /// <summary>The last talking-score line at or before a position.</summary>
    public int LineIndexOf(int bar, int ev)
    {
        int best = 0;
        for (int i = 0; i < _linePositions.Count; i++)
        {
            var (b, e) = _linePositions[i];
            if (b < bar || b == bar && e <= ev) best = i;
            else break;
        }
        return best;
    }
}
