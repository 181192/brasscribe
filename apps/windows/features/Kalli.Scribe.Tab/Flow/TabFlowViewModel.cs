using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;
using Kalli.Scribe.Services;
using Kalli.Scribe.ViewModels;

namespace Kalli.Scribe.Tab;

/// <summary>The screens of a tab app, in the order a player meets them.</summary>
public enum TabScreen { FirstRun, YourInstrument, Home, WhatIsThis, Transcribing, CheckTheSong, Tab, Error }

/// <summary>
/// The flow of an app that writes tab: the first run and Your instrument, then Home (record, open a recording, the
/// library), What is this?, writing the notes down on the computer, Check the song, and the tab, where the song is
/// practised. Owns the child view models; the window binds <see cref="Screen"/> to its pages and moves keyboard focus
/// to each page's heading.
/// </summary>
public sealed partial class TabFlowViewModel : ObservableObject
{
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private readonly Func<Uri, string?, IEngineClient> _engineFactory;
    private readonly SongAnswers<SourceAudio> _answers = new();
    private IEngineClient? _engine;
    private TranscriptionResult? _result;
    private SourceAudio? _source;
    private string? _libraryId;
    /// <summary>Counts the tabs asked for: an answer for an older one is not shown.</summary>
    private int _opening;

    public TabFlowViewModel(Target target, StartViewModel start, TranscriptionViewModel transcription, SettingsViewModel settings,
        YourInstrumentStore instruments, PracticeModel practice, TabExportViewModel export, Func<Uri, string?, IEngineClient> engineFactory,
        IAnnouncer announcer, IStrings strings, ScoreLibrary? library = null)
    {
        Export = export;
        Target = target;
        Start = start;
        Transcription = transcription;
        Settings = settings;
        _engineFactory = engineFactory;
        _announcer = announcer;
        _s = strings;
        Instrument = new YourInstrumentViewModel(instruments, strings);
        WhatIsThis = new WhatIsThisViewModel(strings, _answers, Profiles, target);
        Check = new SongCheckViewModel(strings, Profiles);
        TabPage = new TabPageViewModel(practice, strings, announcer);
        Error = new ErrorViewModel(strings);
        // Every change of the connection: whichever engine answers next is asked for its interface version first, and
        // the computer is asked which profiles it has. Before the library's own handler, which asks that engine too.
        Settings.Connection.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName != nameof(ConnectionMonitor.State)) return;
            _engine = null;
            // A state shown as sample content has no computer behind it to ask.
            if (!Settings.Connection.IsPreview) _ = AskProfilesAsync();
            WhatIsThis.ComputerChanged(ComputerThere);
            Check.Update(ComputerThere);
        };
        LibraryView = new LibraryViewModel(library, target, () => Engine, settings.Connection, announcer, strings, Subtitle);
        LibraryView.ProblemNoticed += (_, text) => ProblemNoticed?.Invoke(this, text);
        Screen = settings.FirstRunDone ? TabScreen.Home : TabScreen.FirstRun;

        Instrument.Done += (_, _) =>
        {
            OnPropertyChanged(nameof(InstrumentSummary));
            Screen = _instrumentFrom;
        };
        Start.SourceReady += (_, source) =>
        {
            _source = source;
            WhatIsThis.Open(source, Instrument.Stored, ComputerThere);
            Screen = TabScreen.WhatIsThis;
            if (!Settings.Connection.IsPreview || Profiles.Answer is null) _ = AskProfilesAsync();
        };
        // A score file is not a recording: this app writes tab from what it hears.
        Start.ScoreOpened += (_, path) =>
        {
            Start.ErrorText = _s.Format("Tab_Error_ScoreFile", Path.GetFileName(path));
            _announcer.Announce(Start.ErrorText, AnnouncementKind.Important);
        };
        WhatIsThis.Chosen += async (_, source) => await WriteDownAsync(source, audioId: null);
        Check.WriteAgain += async (_, options) =>
        {
            if (_source is not { } source || _result is not { } result) return;
            _answers.Set(source, new SongAnswer(options.Recording, options));
            await WriteDownAsync(source, result.AudioId ?? (result.JobId is { } job ? await AudioOnComputerAsync(job) : null));
        };
        Check.ShowTab += async (_, _) => await ShowTabAsync();
        Transcription.Completed += (_, r) =>
        {
            _result = r;
            _source = r.Source;
            _libraryId = null;
            LibraryView.Keep(() => _libraryId = LibraryView.Store?.AddMade(Path.GetFileNameWithoutExtension(r.Source.DisplayName), r.MusicXml, r.Composition,
                1, 0, 0, r.JobId, r.Evidence).Id);
            _ = OpenCheckAsync(r.JobId);
        };
        Transcription.FailedWith += (_, failure) =>
        {
            Error.Show(failure switch
            {
                TranscriptionFailure.ComputerUnreachable => ErrorKind.ComputerUnreachable,
                TranscriptionFailure.RecordingUnreadable => ErrorKind.RecordingUnreadable,
                TranscriptionFailure.UpdateApp => ErrorKind.UpdateApp,
                TranscriptionFailure.UpdateBandroom => ErrorKind.UpdateBandroom,
                _ => ErrorKind.ScoreFailed,
            }, Transcription.ErrorDetail);
            if (failure is TranscriptionFailure.UpdateApp or TranscriptionFailure.UpdateBandroom) Settings.Connection.Kick();
            Screen = TabScreen.Error;
        };
        Transcription.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(TranscriptionViewModel.IsRunning)) BackCommand.NotifyCanExecuteChanged();
        };
        Error.Retry += async (_, _) =>
        {
            if (_source is { } source) await WriteDownAsync(source, _result?.AudioId);
            else Screen = TabScreen.Home;
        };
        Error.Alternative += (_, _) => Screen = TabScreen.Home;
        TabPage.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(TabPageViewModel.Title)) OnPropertyChanged(nameof(Title));
            if (e.PropertyName == nameof(TabPageViewModel.IsReady)) OnPropertyChanged(nameof(CanExport));
        };
    }

    public Target Target { get; }
    public StartViewModel Start { get; }
    public TranscriptionViewModel Transcription { get; }
    public SettingsViewModel Settings { get; }
    public YourInstrumentViewModel Instrument { get; }
    public WhatIsThisViewModel WhatIsThis { get; }
    public SongCheckViewModel Check { get; }
    public TabPageViewModel TabPage { get; }
    public ErrorViewModel Error { get; }
    public LibraryViewModel LibraryView { get; }

    /// <summary>Share or print the tab on screen.</summary>
    public TabExportViewModel Export { get; }

    /// <summary>The tab on screen: its MusicXML, job and what the job wrote (null when not known).</summary>
    private (string MusicXml, string? Job, IReadOnlyCollection<string>? Outputs)? _shown;

    /// <summary>Share or print, for the tab on screen: what can be had now, from this PC and the computer.</summary>
    public void PrepareExport()
    {
        if (_shown is not { } shown) return;
        Export.Prepare(TabPage.Title, shown.MusicXml, shown.Job, shown.Outputs, ComputerThere ? Engine : null);
    }

    /// <summary>Share or print can be opened: a tab is shown.</summary>
    public bool CanExport => Screen == TabScreen.Tab && TabPage.IsReady;

    /// <summary>The profiles of this app's target that the computer in use has.</summary>
    public ComputerProfiles Profiles { get; } = new();

    /// <summary>Something went wrong that the player should see; the window shows it in its notice bar.</summary>
    public event EventHandler<string>? ProblemNoticed;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(BackCommand))]
    [NotifyPropertyChangedFor(nameof(Title), nameof(CanExport))]
    public partial TabScreen Screen { get; set; }

    partial void OnScreenChanged(TabScreen oldValue, TabScreen newValue)
    {
        if (oldValue == TabScreen.Tab && newValue != TabScreen.Tab) TabPage.Leave();
        if (newValue == TabScreen.YourInstrument) Instrument.Reset();
        _announcer.Announce(_s[$"Screen_{newValue}"], AnnouncementKind.Status);
    }

    /// <summary>The window's title for the screen: the song's on the tab, the recording's while it is worked on.</summary>
    public string Title => Screen switch
    {
        TabScreen.Tab => TabPage.Title,
        TabScreen.WhatIsThis or TabScreen.Transcribing or TabScreen.CheckTheSong => _source is { } s ? Path.GetFileNameWithoutExtension(s.DisplayName) : "",
        _ => "",
    };

    /// <summary>Settings' "Your instrument" row: "Guitar, 6 strings · Standard".</summary>
    public string InstrumentSummary => Instrument.Summary(Instrument.Stored);

    /// <summary>The computer is connected (a state shown as sample content counts as there).</summary>
    public bool ComputerThere => Settings.Connection.IsConnected;

    /// <summary>
    /// The client for the engine in use. It keeps the rule that nothing but the heartbeat is asked of an engine with
    /// another interface version, and tells the status row the moment it finds one.
    /// </summary>
    public IEngineClient Engine
    {
        get
        {
            if (_engine is null)
            {
                _engine = _engineFactory(Settings.EngineUri, Settings.EngineToken);
                _engine.InterfaceMismatch = Settings.Connection.Kick;
            }
            return _engine;
        }
    }

    private TabScreen _instrumentFrom = TabScreen.Home;

    /// <summary>First run: Get started asks Your instrument, then Home. Neither is shown again.</summary>
    [RelayCommand]
    private void GetStarted()
    {
        Settings.FirstRunDone = true;
        _instrumentFrom = TabScreen.Home;
        Screen = TabScreen.YourInstrument;
    }

    /// <summary>Your instrument from Settings; Save or Not now comes back where the player was.</summary>
    [RelayCommand]
    private void ChangeInstrument()
    {
        if (Screen == TabScreen.YourInstrument) return;
        _instrumentFrom = Screen;
        Screen = TabScreen.YourInstrument;
    }

    [RelayCommand]
    private void NewSong()
    {
        if (!Transcription.IsRunning) Screen = TabScreen.Home;
    }

    /// <summary>Asks the computer in use which profiles it has; a computer that has answered is not asked again.</summary>
    public async Task AskProfilesAsync()
    {
        if (!ComputerThere) { Profiles.Clear(); return; }
        string computer = Settings.Credentials.CurrentServerId ?? Settings.EngineUri.ToString();
        if (Profiles.Answer is { Asking: false, Listed: not null } known && known.Computer == computer) return;
        Profiles.Asking(computer);
        IReadOnlySet<string>? listed = null;
        try { listed = (await Engine.ListProfilesAsync()).Where(p => Target.Makes(p.Target)).Select(p => p.Name).ToHashSet(); }
        catch (Exception e) when (e is EngineException or HttpRequestException or TaskCanceledException or NotSupportedException
                                   or System.Text.Json.JsonException) { }
        Profiles.Answered(computer, listed);
    }

    /// <summary>Writes the recording down on the computer, for the player's instrument and this song's answers.</summary>
    private async Task WriteDownAsync(SourceAudio source, string? audioId)
    {
        _source = source;
        var options = TabSong.Options(Instrument.Stored, _answers.Of(source));
        string profile = TabSong.Profile(options.Instrument, Profiles.Listed) ?? TabProfiles.Tab;
        string title = Path.GetFileNameWithoutExtension(source.DisplayName);
        Screen = TabScreen.Transcribing;
        await Transcription.RunAsync(source, RecordingLabel(options.Recording), profile,
            uploaded => TabSong.Job(new JobCreate(uploaded, profile, RenderAudio: true, Title: title), options, Profiles.Listed), audioId);
        // Cancelled: back to What is this? with the recording kept.
        if (!Transcription.IsRunning && Screen == TabScreen.Transcribing && Transcription.ErrorText is null)
            Screen = _result?.Source == source ? TabScreen.CheckTheSong : TabScreen.WhatIsThis;
    }

    /// <summary>What was recorded, in the words of What is this?: "A full song", "Just my instrument".</summary>
    public string RecordingLabel(Recording? recording) => _s[recording == Recording.Song ? "Tab_What_Song" : "Tab_What_Instrument"];

    /// <summary>The upload the computer keeps for <paramref name="job"/>: the same recording is written down again without sending it.</summary>
    private async Task<string?> AudioOnComputerAsync(string job)
    {
        try { return (await Engine.GetJobAsync(job)).AudioId; }
        catch (Exception e) when (e is EngineException or HttpRequestException or NotSupportedException) { return null; }
    }

    /// <summary>Check the song for a tab just written: its facts are read from the computer.</summary>
    private async Task OpenCheckAsync(string? job)
    {
        int opening = ++_opening;
        Check.Reading();
        Screen = TabScreen.CheckTheSong;
        if (job is null) { Check.Missing(_s["Tab_Check_NoComputer"]); return; }
        try
        {
            var tab = await Engine.GetTabAsync(job);
            var stages = (await Engine.GetJobAsync(job)).Stages.Select(s => s.Name).ToList();
            if (opening == _opening) Check.Show(tab, stages, ComputerThere);
        }
        catch (EngineException e) when (e.Interface is { } answer)
        {
            if (opening == _opening) Check.Missing(LibraryView.SayUpdate(answer, notice: false));
        }
        catch (Exception e) when (e is EngineException or HttpRequestException or TaskCanceledException or NotSupportedException
                                   or System.Text.Json.JsonException)
        {
            if (opening == _opening) Check.Missing(e is EngineException ee ? EngineErrors.Message(ee, _s) : _s["Error_Unreachable"]);
        }
    }

    /// <summary>The tab of the song in hand.</summary>
    private Task ShowTabAsync() => _result is { } r
        ? OpenTabAsync(r.MusicXml, r.Composition, r.JobId, Path.GetFileNameWithoutExtension(r.Source.DisplayName), r.Source.WavPath, r.Outputs)
        : Task.CompletedTask;

    /// <summary>Shows a tab: read at once from its page, with the computer's data for its marks and its beats when it gives them.</summary>
    private async Task OpenTabAsync(string musicXml, Composition? composition, string? job, string title, string? recording,
        IReadOnlyCollection<string>? outputs = null)
    {
        int opening = ++_opening;
        _shown = (musicXml, job, outputs);
        TabPage.Reading(title);
        Screen = TabScreen.Tab;
        TabResult? data = null;
        if (job is not null && ComputerThere)
        {
            try { data = await Engine.GetTabAsync(job); }
            catch (Exception e) when (e is EngineException or HttpRequestException or TaskCanceledException or NotSupportedException
                                       or System.Text.Json.JsonException) { }
        }
        if (opening != _opening) return;
        TabSheet sheet;
        try { sheet = await Task.Run(() => TabSheet.Read(musicXml, data)); }
        catch (Exception e) when (e is System.Xml.XmlException or FormatException or InvalidOperationException)
        {
            TabPage.Failed();
            return;
        }
        if (opening != _opening) return;
        var songs = LibraryView.Store?.Entries.Select(e => e.JobId).OfType<string>().ToHashSet();
        await TabPage.ShowAsync(sheet, composition, job ?? _libraryId ?? title, job, recording, songs);
    }

    /// <summary>What is this? for <paramref name="source"/>, with the computer's profiles as given (the sample scenes).</summary>
    public void ShowWhatIsThis(SourceAudio source, IReadOnlySet<string>? listed)
    {
        _source = source;
        Profiles.Asking(Settings.EngineUri.ToString());
        Profiles.Answered(Settings.EngineUri.ToString(), listed);
        WhatIsThis.Open(source, Instrument.Stored, ComputerThere);
        Screen = TabScreen.WhatIsThis;
    }

    /// <summary>Check the song for a tab's facts as given (the sample scenes).</summary>
    public void ShowCheck(TabResult tab, IReadOnlyList<string> stages)
    {
        Profiles.Asking(Settings.EngineUri.ToString());
        Profiles.Answered(Settings.EngineUri.ToString(), new HashSet<string> { TabProfiles.Tab });
        Check.Show(tab, stages, ComputerThere);
        Screen = TabScreen.CheckTheSong;
    }

    /// <summary>A tab with its data as given, without its recording (the sample scenes).</summary>
    public async Task ShowTabAsync(string musicXml, TabResult tab, Composition? composition, string title)
    {
        int opening = ++_opening;
        _shown = (musicXml, null, null);
        TabPage.Reading(title);
        Screen = TabScreen.Tab;
        var sheet = await Task.Run(() => TabSheet.Read(musicXml, tab));
        if (opening == _opening) await TabPage.ShowAsync(sheet, composition, title, null, null, null);
    }

    [RelayCommand]
    private void OpenLibraryItem(LibraryItem? item) => _ = OpenLibraryItemAsync(item);

    /// <summary>Opens a row: a song on the computer is downloaded into the library first.</summary>
    public async Task OpenLibraryItemAsync(LibraryItem? item)
    {
        if (item is null) return;
        if (item.OnComputer && item.JobId is { } jobId)
        {
            try
            {
                var (job, composition, xml, evidence) = await LibraryView.DownloadAsync(jobId);
                _result = null;
                _source = null;
                _libraryId = LibraryView.Store?.AddMade(job.Title ?? item.Title, xml, composition, 1, 0, 0, jobId, evidence).Id;
                await OpenTabAsync(xml, composition, jobId, job.Title ?? item.Title, null, job.Outputs);
            }
            catch (EngineException e) when (e.Interface is { } answer)
            {
                Start.ErrorText = LibraryView.SayUpdate(answer, notice: false);
            }
            catch (Exception e) when (e is EngineException or HttpRequestException or IOException or FormatException
                                       or System.Xml.XmlException or System.Text.Json.JsonException)
            {
                Start.ErrorText = _s.Format("Start_Error_Score", item.Title);
                _announcer.Announce(Start.ErrorText, AnnouncementKind.Important);
            }
            return;
        }
        if (LibraryView.Store?.Entries.FirstOrDefault(e => e.Id == item.Id) is not { } entry) return;
        try
        {
            string xml = await File.ReadAllTextAsync(entry.MusicXmlPath);
            var composition = entry.CompositionPath is { } c && File.Exists(c) ? CompositionJson.Parse(await File.ReadAllTextAsync(c)) : null;
            _result = null;
            _source = null;
            _libraryId = entry.Id;
            await OpenTabAsync(xml, composition, entry.JobId, entry.Title, null);
        }
        catch (Exception e) when (e is IOException or FormatException or System.Xml.XmlException or UnauthorizedAccessException
                                   or System.Text.Json.JsonException)
        {
            Start.ErrorText = _s.Format("Start_Error_Score", entry.Title);
            _announcer.Announce(Start.ErrorText, AnnouncementKind.Important);
        }
    }

    /// <summary>"Edit title" on a row; a song from the computer is renamed there too.</summary>
    public async Task<bool> RenameLibraryItemAsync(LibraryItem item, string title)
    {
        string cleaned = title.Trim();
        if (cleaned.Length == 0) return false;
        if (item.OnComputer)
        {
            if (item.JobId is not { } jobId || !await LibraryView.RenameOnComputerAsync(jobId, cleaned)) return false;
            await LibraryView.RefreshComputerAsync();
            return true;
        }
        var entry = LibraryView.Store?.Entries.FirstOrDefault(e => e.Id == item.Id);
        if (entry is null || !LibraryView.RenameHere(item.Id, cleaned)) return false;
        if (_libraryId == item.Id && Screen == TabScreen.Tab) TabPage.Title = cleaned;
        if (entry.JobId is { } job) _ = LibraryView.RenameOnComputerAsync(job, cleaned);
        return true;
    }

    /// <summary>"Delete" on a row: this PC's copy, or the run on the computer; the tab on screen closes with its copy.</summary>
    public Task<bool> DeleteLibraryItemAsync(LibraryItem item) => LibraryView.DeleteAsync(item, removedHere: () =>
    {
        if (_libraryId != item.Id) return;
        _libraryId = null;
        if (Screen == TabScreen.Tab) Screen = TabScreen.Home;
    });

    /// <summary>A row's line in the library: "6-string guitar · Drop D · 3 notes to check · Today".</summary>
    private string Subtitle(LibraryEntry e)
    {
        string when = LibraryViewModel.WhenText(e.Updated, _s);
        if (!e.IsAvailable) return _s["Library_Unavailable"];
        SongFacts? facts = null;
        try
        {
            if (File.Exists(e.MusicXmlPath))
                facts = SongFacts.Of(File.ReadAllText(e.MusicXmlPath), e.CompositionPath is { } c && File.Exists(c) ? File.ReadAllText(c) : null);
        }
        catch (Exception x) when (x is IOException or UnauthorizedAccessException) { }
        if (facts is null) return string.Join(" · ", _s["Tab_Song"], when);
        var parts = new List<string>
        {
            facts.Kind is { } kind ? KindName(kind) : _s["Tab_Song"],
        };
        if (facts.Tuning is { } t) parts.Add(YourInstrumentViewModel.TuningName(t, _s));
        if (facts.ToCheck > 0) parts.Add(_s.Format(facts.ToCheck == 1 ? "Tab_ToCheck_One" : "Tab_ToCheck", facts.ToCheck));
        parts.Add(when);
        return string.Join(" · ", parts);
    }

    private string KindName(FrettedInstrument kind) => YourInstrument.StringsOf(kind) is { } n && Instruments.Of(kind) is { } i
        ? _s.Format($"Tab_KindWithStrings_{i}", n)
        : _s[$"Tab_Kind_{kind}"];

    [RelayCommand(CanExecute = nameof(CanGoBack))]
    private void Back()
    {
        Screen = Screen switch
        {
            TabScreen.WhatIsThis => TabScreen.Home,
            TabScreen.Transcribing => _result is not null ? TabScreen.CheckTheSong : TabScreen.WhatIsThis,
            TabScreen.CheckTheSong => TabScreen.Home,
            TabScreen.Tab when TabPage.IsFullScreen => LeaveFullScreen(),
            TabScreen.Tab => _result is not null ? TabScreen.CheckTheSong : TabScreen.Home,
            TabScreen.Error => TabScreen.Home,
            TabScreen.YourInstrument => _instrumentFrom,
            _ => Screen,
        };
    }

    private TabScreen LeaveFullScreen()
    {
        TabPage.IsFullScreen = false;
        return TabScreen.Tab;
    }

    /// <summary>Back works everywhere but Home and the first run, and while the notes are written down (Cancel is the way out then).</summary>
    private bool CanGoBack() => Screen is TabScreen.WhatIsThis or TabScreen.CheckTheSong or TabScreen.Tab or TabScreen.Error or TabScreen.YourInstrument
                                || Screen == TabScreen.Transcribing && !Transcription.IsRunning;

    /// <summary>For tests: the last song written down.</summary>
    public TranscriptionResult? LastResult => _result;
}
