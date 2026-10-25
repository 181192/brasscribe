using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;
using Kalli.Scribe.Services;

namespace Kalli.Scribe.Tab;

/// <summary>A tab ready to show: the page, what the page says about its own notes, the data when the computer gave it, and the marks.</summary>
public sealed class TabSheet(string musicXml, TabIndex index, TabResult? tab, TabMarks marks)
{
    public string MusicXml { get; } = musicXml;
    public TabIndex Index { get; } = index;
    public TabResult? Tab { get; } = tab;
    public TabMarks Marks { get; } = marks;

    public TabLayout Layout => Tab is { Layout: not TabLayout.Unknown } t ? t.Layout
        : Index.TabStaff is null ? TabLayout.Notation
        : Index.Staves > 1 ? TabLayout.TabAndNotation
        : TabLayout.Tab;

    /// <summary>The tuning's id ("drop-d") when it is one the app has words for; else the name the page or the data gives.</summary>
    public string Tuning
    {
        get
        {
            if (Tab?.Preset is { } preset && SongCheck.TuningOf(preset) is { } fromData) return fromData;
            var open = SongFacts.OpenStringsOf(MusicXml);
            foreach (var (tuning, strings) in SongFacts.OpenStrings)
                if (strings.SequenceEqual(open) && SongCheck.TuningOf(tuning) is { } fromPage) return fromPage;
            return Tab?.Instrument.Tuning.Name ?? Index.TuningName ?? FrettedInstruments.StandardTuning;
        }
    }

    public int Capo => Tab?.Instrument.Capo ?? Index.Capo;

    /// <summary>Quarter notes a minute.</summary>
    public int? Tempo => Tab is { } t ? TabIndex.Round(t.TempoBpm) : Index.Tempo;

    /// <summary>The page read, with the tab's data when <paramref name="tab"/> gives it; without it the page's own marks.</summary>
    public static TabSheet Read(string musicXml, TabResult? tab)
    {
        var index = TabIndex.Parse(musicXml);
        return new TabSheet(musicXml, index, tab, TabMarks.Of(index, tab));
    }
}

/// <summary>One mark on the page that can be reached from the list: its column and what it says.</summary>
public sealed record TabMarkItem(int Column, int Bar, string Label);

/// <summary>
/// The tab screen: the page to read, the tuning and capo above it, what there is to check, and the song practised with
/// its recording (speed with the pitch kept, a bar back or on, the bars to repeat). The page is drawn by the app; this
/// is what it shows and where the song is.
/// </summary>
public sealed partial class TabPageViewModel : ObservableObject, IDisposable
{
    private readonly IStrings _s;
    private readonly IAnnouncer _announcer;

    public TabPageViewModel(PracticeModel practice, IStrings strings, IAnnouncer announcer)
    {
        Practice = practice;
        _s = strings;
        _announcer = announcer;
        Practice.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName is nameof(PracticeModel.Speed)) OnPropertyChanged(nameof(SpeedText));
            if (e.PropertyName is nameof(PracticeModel.Recording)) { OnPropertyChanged(nameof(RecordingText)); OnPropertyChanged(nameof(CanPlay)); OnPropertyChanged(nameof(CanFetch)); }
            if (e.PropertyName is nameof(PracticeModel.Repeat)) OnPropertyChanged(nameof(RepeatText));
            if (e.PropertyName is nameof(PracticeModel.Playing)) OnPropertyChanged(nameof(PlayLabel));
            if (e.PropertyName is nameof(PracticeModel.At) or nameof(PracticeModel.Jumps)) UpdatePlace();
        };
    }

    public PracticeModel Practice { get; }

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsReady), nameof(Chip), nameof(Summary), nameof(Bars))]
    public partial TabSheet? Sheet { get; set; }

    /// <summary>The recording's beats in the tab: the cursor and the bar-by-bar steps need them.</summary>
    public TabClock? Clock { get; private set; }

    [ObservableProperty] public partial string Title { get; set; } = "";

    /// <summary>The page is being read; the computer is asked for the tab's notes.</summary>
    [ObservableProperty] public partial bool IsReading { get; set; }

    /// <summary>The page could not be read.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasFailed))]
    public partial string? FailedText { get; set; }

    public bool HasFailed => FailedText is not null;

    public bool IsReady => Sheet is not null;

    /// <summary>"Drop D · capo 2" above the page.</summary>
    public string Chip => Sheet is not { } s ? ""
        : _s.Format("Tab_Chip", YourInstrumentViewModel.TuningName(s.Tuning, _s), s.Capo == 0 ? _s["Tab_NoCapo"] : _s.Format("Tab_Capo", s.Capo));

    /// <summary>What there is to check: "3 notes marked ? · 1 note with no place"; empty when nothing is.</summary>
    public string Summary
    {
        get
        {
            if (Sheet is not { } s) return "";
            var parts = new List<string>();
            if (s.Marks.Doubtful > 0) parts.Add(_s.Format(s.Marks.Doubtful == 1 ? "Tab_Marked_One" : "Tab_Marked", s.Marks.Doubtful));
            if (s.Marks.NoPlace > 0) parts.Add(_s.Format(s.Marks.NoPlace == 1 ? "Tab_NoPlaceCount_One" : "Tab_NoPlaceCount", s.Marks.NoPlace));
            return string.Join(" · ", parts);
        }
    }

    /// <summary>The bars of the page, for the repeat's choices.</summary>
    public int Bars => Sheet?.Index.Bars ?? 0;

    /// <summary>The marks to step through with Next ?, in the order of the page.</summary>
    public ObservableCollection<TabMarkItem> Marks { get; } = [];

    /// <summary>"Bar 3, beat 2" where the song is.</summary>
    [ObservableProperty] public partial string PlaceText { get; set; } = "";

    /// <summary>The bar the song is in (from 0); the page keeps it in view.</summary>
    [ObservableProperty] public partial int Bar { get; set; }

    /// <summary>The page's size in per cent.</summary>
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(ZoomText))]
    public partial int Zoom { get; set; } = 100;

    public string ZoomText => _s.Format("Tab_Zoom", Zoom);

    /// <summary>The tab takes the whole window, the chrome hidden until asked for.</summary>
    [ObservableProperty] public partial bool IsFullScreen { get; set; }

    public string SpeedText => _s.Format("Tab_Practice_Speed", Practice.Speed);

    public string PlayLabel => Practice.Playing ? _s["Tab_Practice_Pause"] : _s["Tab_Practice_Play"];

    public string? RepeatText => Practice.Repeat is { } r
        ? r.First == r.Last ? _s.Format("Tab_Practice_RepeatOn_One", Number(r.First)) : _s.Format("Tab_Practice_RepeatOn", Number(r.First), Number(r.Last))
        : null;

    public bool CanPlay => Practice.Recording == RecordingState.Here && Clock is not null;

    /// <summary>The recording is not on this PC, and the computer may still have it.</summary>
    public bool CanFetch => Practice.Recording is RecordingState.NotHere or RecordingState.NoAnswer && JobId is not null;

    /// <summary>What is known of the recording, when it is not simply there; null when it plays.</summary>
    public string? RecordingText => Practice.Recording == RecordingState.Here ? (Clock is null ? _s["Tab_Practice_NoBeats"] : null)
        : _s[$"Tab_Practice_{Practice.Recording}"];

    /// <summary>The job of the song on the computer; null for a song that came as a file.</summary>
    public string? JobId { get; private set; }

    /// <summary>The page is about to be read: <paramref name="title"/> is the song's.</summary>
    public void Reading(string title)
    {
        Title = title;
        IsReading = true;
        FailedText = null;
        Sheet = null;
        Marks.Clear();
    }

    /// <summary>
    /// The page to show. <paramref name="job"/> is its job on the computer, <paramref name="recording"/> the recording's
    /// file when the app has it, and <paramref name="songs"/> the jobs of the library, whose recordings are kept.
    /// </summary>
    public async Task ShowAsync(TabSheet sheet, Composition? composition, string song, string? job, string? recording, IReadOnlySet<string>? songs)
    {
        IsReading = false;
        JobId = job;
        Clock = TabClock.Of(sheet.Index, sheet.Tab, composition);
        Sheet = sheet;
        Marks.Clear();
        for (int i = 0; i < sheet.Marks.Columns.Count; i++)
        {
            var c = sheet.Marks.Columns[i];
            Marks.Add(new TabMarkItem(i, c.Bar, _s.Format(c.Kind == MarkKind.NoPlace ? "Tab_Mark_NoPlace" : "Tab_Mark_NotSure", c.BarNumber, c.Beat)));
        }
        OnPropertyChanged(nameof(CanPlay));
        await Practice.OpenAsync(song, job, Clock, recording, songs);
        UpdatePlace();
    }

    /// <summary>The page could not be read: said, and the screen says what to do.</summary>
    public void Failed()
    {
        IsReading = false;
        FailedText = _s["Tab_Failed"];
        _announcer.Announce(FailedText, AnnouncementKind.Important);
    }

    private void UpdatePlace()
    {
        if (Clock is not { } clock || Sheet is not { } sheet) { PlaceText = ""; return; }
        var place = clock.PlaceAt(Practice.Now());
        Bar = place.Bar;
        var m = sheet.Index.Measures[Math.Clamp(place.Bar, 0, sheet.Index.Measures.Count - 1)];
        PlaceText = m.Pickup ? _s.Format("Tab_PickupBeat", clock.BeatAt(place))
            : _s.Format("Tab_BarBeat", m.Number, clock.BeatAt(place));
    }

    /// <summary>The place again while it plays (the view asks on every frame it draws the cursor).</summary>
    public void Tick() => UpdatePlace();

    private string Number(int bar) => Sheet is { } s && bar >= 0 && bar < s.Index.Measures.Count ? s.Index.Measures[bar].Number : (bar + 1).ToString(System.Globalization.CultureInfo.CurrentCulture);

    [RelayCommand] private void PlayPause() => Practice.Toggle();
    [RelayCommand] private void ToStart() => Practice.ToStart();
    [RelayCommand] private void PreviousBar() => Practice.Step(-1);
    [RelayCommand] private void NextBar() => Practice.Step(1);
    [RelayCommand] private void Slower() => Practice.Slower();
    [RelayCommand] private void Faster() => Practice.Faster();
    [RelayCommand] private void StopRepeat() => Practice.SetRepeat(null);
    [RelayCommand] private void ZoomIn() => Zoom = Math.Min(Zoom + 25, 300);
    [RelayCommand] private void ZoomOut() => Zoom = Math.Max(Zoom - 25, 50);
    [RelayCommand] private void FullScreen() => IsFullScreen = !IsFullScreen;

    /// <summary>Repeats the bars from <paramref name="first"/> to <paramref name="last"/> (from 0, in either order).</summary>
    public void RepeatBars(int first, int last)
    {
        if (Bars == 0) return;
        int a = Math.Clamp(Math.Min(first, last), 0, Bars - 1), b = Math.Clamp(Math.Max(first, last), 0, Bars - 1);
        Practice.SetRepeat(new RepeatBars(a, b));
        if (RepeatText is { } said) _announcer.Announce(said);
    }

    /// <summary>One bar again and again, slowly: to listen to a note the tab is not sure of.</summary>
    public void PlayBarSlowly(int bar) => Practice.PlayBarSlowly(bar);

    /// <summary>The screen is left: the sound stops, and the song is kept where it was.</summary>
    public void Leave()
    {
        Practice.Leave();
        IsFullScreen = false;
    }

    public void Dispose() => Practice.Dispose();
}
