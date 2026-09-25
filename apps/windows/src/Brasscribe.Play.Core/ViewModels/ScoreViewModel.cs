using System.Collections.ObjectModel;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.TalkingScore;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

public sealed record ScorePartItem(int Index, string Name, string? Instrument, int UncertainCount);

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
    }

    public PlayerViewModel Player { get; }
    public IOriginalPlayer? Original { get; }
    public TalkingScoreDocument? Document { get; private set; }
    public Composition? Composition { get; private set; }
    public string? MusicXml { get; private set; }
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
        Player.Load(System.Text.Encoding.UTF8.GetBytes(musicXml));
        Player.PlayAlongPart = Player.Parts.FirstOrDefault(p => p.Name.Contains("Solo", StringComparison.OrdinalIgnoreCase)) ?? Player.Parts.FirstOrDefault();
        IsLoaded = true;
        UpdateUncertain();
        Sync(_nav.Text, announce: false);
        RebuildTalkingLines();
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

    partial void OnSelectedPartIndexChanged(int value)
    {
        if (_nav is null || value < 0) return;
        _nav.GoToPart(value);
        var part = Document!.Parts[value];
        string name = Language == "nb" ? part.NameNb ?? part.Name : part.Name;
        string mode = _nav.SetPitchMode(ConcertPitch ? PitchMode.Concert : PitchMode.Written);
        _announcer.Announce(_s.Format("Score_PartShown", name) + " " + mode);
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
            case ScoreCommand.PlayPause: Player.PlayPauseCommand.Execute(null); break;
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

    [RelayCommand]
    public void GoToBar(int number)
    {
        if (_nav is null) return;
        var r = _nav.GoToBar(number);
        if (r.Moved) Sync(r.Text, announce: true);
        else _announcer.Announce(r.Text, AnnouncementKind.Important);
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

    /// <summary>"Listen to this bar": the original recording when it is loaded and timed, else the score, looped.</summary>
    [RelayCommand]
    private void ListenToBar()
    {
        if (_nav is null) return;
        int bar = _nav.Bar.Number;
        if (Original is { HasMedia: true } && BarSeconds(_nav.PartIndex, _nav.BarIndex) is { } span)
        {
            Original.PlayRange(TimeSpan.FromSeconds(span.Start), TimeSpan.FromSeconds(span.End), loop: true);
            _announcer.Announce(_s.Format("Score_ListeningOriginal", bar));
        }
        else
        {
            Player.PlayBar(bar);
            _announcer.Announce(_s.Format("Score_ListeningScore", bar));
        }
    }

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
        Announcement = text;
        CurrentBar = _nav!.Bar.Number;
        CurrentPartIndex = _nav.PartIndex;
        CurrentLineIndex = LineIndexOf(_nav.BarIndex, _nav.EventIndex);
        CursorMoved?.Invoke(this, text);
        if (announce) _announcer.Announce(text);
    }

    private void UpdateUncertain()
    {
        UncertainLeft = _nav?.UncertainCount ?? 0;
        UncertainText = _s.Format("Score_UncertainLeft", UncertainLeft);
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
