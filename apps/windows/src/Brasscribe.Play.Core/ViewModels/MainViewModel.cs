using Brasscribe.Play.Core.Arrangement;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Seats;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>The screens of the Play flow (design/system.md §3). The part view is the score screen with one part chosen.</summary>
public enum Screen { Start, SourceKind, Transcribing, Score, FirstRun, Review, Error, ChooseOutput, WhatDoYouPlay }

/// <summary>
/// The flow of the app: start (import or record) → "What is this?" → transcription → score.
/// Owns the child view models and the engine client; the WinUI shell binds <see cref="Screen"/> to
/// its navigation and moves keyboard focus to each screen's heading.
/// </summary>
/// <summary>A row of "Your scores": a score on this PC, or a finished score on the paired computer.</summary>
public sealed record LibraryItem(string Id, string Title, string Subtitle, bool OnComputer = false, string? JobId = null)
{
    public bool OnThisPc => !OnComputer;
}

public sealed partial class MainViewModel : ObservableObject
{
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private readonly Func<Uri, string?, IEngineClient> _engineFactory;
    private IEngineClient? _engine;
    private TranscriptionResult? _result;

    public MainViewModel(
        StartViewModel start, SourceKindViewModel kind, TranscriptionViewModel transcription, ScoreViewModel score,
        ExportViewModel export, OutputOptionsViewModel output, SettingsViewModel settings,
        Func<Uri, string?, IEngineClient> engineFactory, IAnnouncer announcer, IStrings strings, ICoreBridge core,
        ScoreLibrary? library = null)
    {
        Start = start;
        Kind = kind;
        Transcription = transcription;
        Score = score;
        Export = export;
        Output = output;
        Settings = settings;
        Core = core;
        _engineFactory = engineFactory;
        _announcer = announcer;
        _s = strings;
        Review = new ReviewViewModel(score, announcer, strings);
        Seats = new SeatCatalog(core, strings);
        // "Your part": the part chosen for this score, else the seat's part in the lineup shown (the core's table).
        Score.PartLabel = PartLabel;
        Score.MyPartReadsBass = () => Output.Applied.Reads == "bass";
        Score.YourPartResolver = parts => YourPart.Resolve(core, Settings.SeatChoice, ShownLineup, parts, _myPartOverride);
        Score.YourPartNoticeText = (parts, result) => YourPart.Notice(_s, Seats, Settings.SeatChoice, result, parts, PartLabel);
        Score.PersistMyPart = name =>
        {
            _myPartOverride = name;
            if (_libraryId is { } id) Keep(() => Library?.SetMyPart(id, name));
        };
        Output.Seats = Seats;
        Output.PartLabel = PartLabel;
        Output.PlayerSeat = settings.SeatChoice;
        // A changed note arranges the whole score again from the Composition (the native core), with the
        // lineup, difficulty and key the shown score was arranged with.
        Score.Rearrange = composition =>
        {
            if (!core.IsNative) return null;
            try { return core.ArrangeMusicXmlWith(composition, Output.Applied); }
            catch (Bridge.CoreBridgeException e)
            {
                _announcer.Announce(Brasscribe.Play.Core.Engine.EngineErrors.CoreMessage(e.Message, _s), AnnouncementKind.Important);
                return null;
            }
        };
        Error = new ErrorViewModel(strings);
        Library = library;
        Score.PersistEditedScore = (xml, compositionJson) =>
        {
            if (_libraryId is { } id) Keep(() => Library?.SaveMusicXml(id, xml, compositionJson, Output.Applied.Lineup));
        };
        Score.PersistEvidence = evidence =>
        {
            if (_libraryId is { } id) Keep(() => Library?.SaveEvidence(id, evidence));
        };
        Score.PersistReviewChanges = changes =>
        {
            if (_libraryId is { } id) Library?.SaveReviewChanges(id, changes);
        };
        RefreshLibrary();
        if (library is not null) library.Changed += (_, _) => RefreshLibrary();
        Screen = settings.FirstRunDone ? Screen.Start : Screen.FirstRun;

        // After a new score: check the notes, then "How should the score be?", then the score.
        Review.Finished += (_, _) =>
        {
            Screen = _chooseOutputNext ? Screen.ChooseOutput : Screen.Score;
            _chooseOutputNext = false;
            UpdateLibraryCount();
        };
        Output.ShowScoreRequested += (_, _) => Screen = Screen.Score;
        Review.ShowMyPartRequested += (_, _) =>
        {
            // Like finishing the review, but straight to the player's part.
            _chooseOutputNext = false;
            UpdateLibraryCount();
            Screen = Screen.Score;
            if (Score.MyPartIndex >= 0) Score.SelectedPartIndex = Score.MyPartIndex;
        };
        Score.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName is nameof(ScoreViewModel.Title) or nameof(ScoreViewModel.IsLoaded)) UpdateOutputContext();
        };
        Score.Player.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(PlayerViewModel.PlayAlongPart)) UpdateOutputContext();
        };
        Error.Retry += async (_, _) =>
        {
            if (_lastChoice is { } choice)
            {
                BeginTake(choice.Kind.Profile);
                Screen = Screen.Transcribing;
                await Transcription.RunAsync(choice.Source, choice.Kind, Output.Options);
            }
            else Screen = Screen.Start;
        };
        Error.Alternative += (_, _) => Screen = Screen.Start;
        Transcription.FailedWith += (_, failure) =>
        {
            Error.Show(failure switch
            {
                TranscriptionFailure.ComputerUnreachable => ErrorKind.ComputerUnreachable,
                TranscriptionFailure.RecordingUnreadable => ErrorKind.RecordingUnreadable,
                _ => ErrorKind.ScoreFailed,
            }, Transcription.ErrorDetail);
            Screen = Screen.Error;
        };

        Start.SourceReady += async (_, src) =>
        {
            Kind.Source = src;
            Kind.Selected = null;
            Kind.IsPercussionSeat = IsPercussionSeat;
            Kind.SetWhere(Settings.EngineUri);
            Screen = Screen.SourceKind;
            await Kind.RefreshFromEngineAsync(Engine);
        };
        Start.ScoreOpened += (_, path) => OpenScoreFile(path);
        // "Change what I play" on "What is this?" goes through Settings: the refusal follows the answer.
        Settings.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(SettingsViewModel.SeatChoice)) Kind.IsPercussionSeat = IsPercussionSeat;
        };
        Kind.Chosen += async (_, choice) =>
        {
            // A drummer's solo take is no drum part: refused before anything is sent (the screen says so too).
            if (choice.Kind.Kind == SourceKind.Solo && IsPercussionSeat)
            {
                _announcer.Announce(_s["Error_PercussionSolo"], AnnouncementKind.Important);
                return;
            }
            _lastChoice = choice;
            _result = null;
            // A solo take has no harmony for a quartet; a quartet chosen for an earlier take goes back to the band.
            BeginTake(choice.Kind.Profile);
            Screen = Screen.Transcribing;
            await Transcription.RunAsync(choice.Source, choice.Kind, Output.Options);
            if (!Transcription.IsRunning && _result is null && Screen == Screen.Transcribing && Transcription.ErrorText is null)
                Screen = Screen.SourceKind; // cancelled: back to the choice, source kept
        };
        Transcription.Completed += (_, r) =>
        {
            bool rearranged = _result is not null && r.AudioId is not null && r.AudioId == _result.AudioId;
            _result = r;
            Output.IsSoloTake = Lineups.IsSoloTake(r.Composition, r.Profile);
            Output.IsBandTake = Lineups.IsBandTake(r.Composition, r.Profile);
            Output.HasSoloist = Lineups.HasSoloist(r.Composition, r.Profile);
            Output.HasEngineJob = r.AudioId is not null;
            Output.ShowingMade(r.Options ?? ArrangementOptions.Default);
            if (!rearranged) _myPartOverride = null;
            // An engine from before seats ignores them: say so once, rather than a silent Solo Cornet part.
            Output.StatusText = null;
            // Only where the seat changes the notes (a solo take, or the tune on the seat): on a band take it changes none.
            // An engine from before the trumpet refused it and wrote the Solo Cornet part: that is said too.
            if (r.SeatFellBack || r.Options is { Seat: not null, Lead: "seat" } && Lineups.RecordedSeat(r.Composition) is null)
            {
                Output.StatusText = _s["Output_OldComputer"];
                _announcer.Announce(Output.StatusText, AnnouncementKind.Important);
            }
            Output.Title = r.Composition.Title;
            Output.LayerSource = r.JobId is { Length: > 0 } jobId && LayerCacheRoot is { } cache
                ? ct => EngineLayerSource.LoadAsync(Engine, jobId, cache, ct)
                : null;
            Score.Original?.Open(r.Source.OriginalPath ?? r.Source.WavPath, r.Source.HasVideo);
            if (Score.Original is { } original) _ = RecordingLevel.ApplyAsync(original, r.Source.WavPath);
            Score.Evidence = r.Evidence;
            Score.Load(r.MusicXml, r.Composition);
            _libraryId = null;
            Keep(() => _libraryId = Library?.AddMade(Score.Title is { Length: > 0 } t ? t : r.Source.DisplayName, r.MusicXml, r.Composition,
                Score.Parts.Count, Score.Player.BarCount, Score.UncertainLeft, r.JobId, r.Evidence,
                Lineups.Engine(Lineups.Recorded(r.Composition) ?? Output.AppliedLineup)).Id);
            // A new score, or the notes written again for other choices: no "was" from before applies.
            ForgetReviewChanges();
            OpenReviewOrScore(rearranged);
        };
        Transcription.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(TranscriptionViewModel.IsRunning)) BackCommand.NotifyCanExecuteChanged();
        };
        Output.Arranged += (_, xml) =>
        {
            // Arranged from the Composition, which has the changed notes: they stay changed, and Review finds
            // them by their Composition note.
            Score.Load(xml, Score.Composition);
            Screen = Screen.Score;
        };
        Output.ArrangedBand += (_, band) =>
        {
            Score.Load(band.MusicXml, core.ParseComposition(band.CompositionJson));
            // Arranged again from the recording's layers, without the notes changed here.
            ForgetReviewChanges();
            Screen = Screen.Score;
        };
        Output.RearrangeRequested += async (_, options) =>
        {
            if (_result is not { } previous) return;
            Screen = Screen.Transcribing;
            await Transcription.RearrangeAsync(previous, options);
            if (!Transcription.IsRunning && Transcription.ErrorText is null && Screen == Screen.Transcribing)
                Screen = Screen.Score; // cancelled: back to the score as it was
        };
        Settings.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName is nameof(SettingsViewModel.EngineAddress) or nameof(SettingsViewModel.EngineToken)) _engine = null;
            if (e.PropertyName == nameof(SettingsViewModel.SingleKeyShortcuts)) Score.SingleKeyShortcuts = Settings.SingleKeyShortcuts;
            if (e.PropertyName == nameof(SettingsViewModel.Verbosity)) Score.Verbosity = Settings.Verbosity;
            if (e.PropertyName == nameof(SettingsViewModel.StandKeepControls)) Score.Stand.KeepControlsVisible = Settings.StandKeepControls;
            if (e.PropertyName == nameof(SettingsViewModel.StandTurnPages)) Score.Stand.TurnPagesWhilePlaying = Settings.StandTurnPages;
            if (e.PropertyName == nameof(SettingsViewModel.SeatChoice))
            {
                // New takes start from the answer; the shown score keeps its arrangement, only "your part" follows.
                Output.PlayerSeat = Settings.SeatChoice;
                Score.RefreshYourPart();
            }
        };
        Score.SingleKeyShortcuts = Settings.SingleKeyShortcuts;
        Score.Verbosity = Settings.Verbosity;
        Score.Stand.KeepControlsVisible = Settings.StandKeepControls;
        Score.Stand.TurnPagesWhilePlaying = Settings.StandTurnPages;
        Score.Stand.HintSeen = Settings.StandHintSeen;
        Score.Stand.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(MusicStandViewModel.HintSeen) && Score.Stand.HintSeen) Settings.StandHintSeen = true;
        };
    }

    public StartViewModel Start { get; }
    public SourceKindViewModel Kind { get; }
    public TranscriptionViewModel Transcription { get; }
    public ScoreViewModel Score { get; }
    public ExportViewModel Export { get; }
    public OutputOptionsViewModel Output { get; }
    public SettingsViewModel Settings { get; }
    public ICoreBridge Core { get; }

    /// <summary>Folder for layer inputs fetched from engine jobs (on-device re-arrangement); null disables it.</summary>
    public string? LayerCacheRoot { get; set; }

    public ReviewViewModel Review { get; }

    /// <summary>The seats of the band for "What do you play?" (the core's table).</summary>
    public SeatCatalog Seats { get; }

    /// <summary>The first run's "What do you play?"; made when the screen opens.</summary>
    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(ContinueWithSeatCommand))]
    public partial SeatPickerViewModel? FirstRunSeat { get; set; }

    partial void OnFirstRunSeatChanged(SeatPickerViewModel? oldValue, SeatPickerViewModel? newValue)
    {
        if (oldValue is not null) oldValue.PropertyChanged -= OnFirstRunSeatPropertyChanged;
        if (newValue is not null) newValue.PropertyChanged += OnFirstRunSeatPropertyChanged;
    }

    private void OnFirstRunSeatPropertyChanged(object? sender, System.ComponentModel.PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(SeatPickerViewModel.CanContinue)) ContinueWithSeatCommand.NotifyCanExecuteChanged();
    }

    private bool CanContinueWithSeat() => FirstRunSeat?.CanContinue == true;

    /// <summary>A picker for Settings, starting from the current answer; nothing changes until it is saved.</summary>
    public SeatPickerViewModel NewSeatPicker() => new(Seats, _s, Settings.SeatChoice);

    /// <summary>A part's name in the UI language, from the core's one table (never an app copy).</summary>
    public string PartLabel(string name) => Score.Language == "nb" ? Core.PartNameNb(name) : name;

    /// <summary>The part chosen for the shown score with "Make this my part"; null follows the seat.</summary>
    private string? _myPartOverride;

    /// <summary>A new take: the quartet only for a group, and the player's seat as Settings has it.</summary>
    /// <summary>The player's seat is percussion (a seat with no clef to read).</summary>
    public bool IsPercussionSeat => Seats.Find(Settings.SeatChoice.SeatId) is { IsPercussion: true };

    private void BeginTake(string profile)
    {
        Output.IsSoloTake = Lineups.IsSoloTake(null, profile);
        Output.IsBandTake = Lineups.IsBandTake(null, profile);
        Output.HasSoloist = profile == "orchestra-with-soloist";
        Output.BeginTake();
    }
    public ErrorViewModel Error { get; }
    public ScoreLibrary? Library { get; }

    /// <summary>"Your scores" in the sidebar and on Home, newest first.</summary>
    public System.Collections.ObjectModel.ObservableCollection<LibraryItem> LibraryItems { get; } = [];

    private (SourceAudio Source, SourceKindOption Kind)? _lastChoice;
    private string? _libraryId;

    public bool RenameCurrentScore(string title)
    {
        string cleaned = title.Trim();
        if (cleaned.Length == 0 || _libraryId is not { } id || Library is null || Score.MusicXml is null) return false;
        try
        {
            Library.Rename(id, cleaned);
            if (Score.Composition is { } composition) composition.Title = cleaned;
            var entry = Library.Entries.FirstOrDefault(e => e.Id == id);
            if (entry is null) return false;
            Score.Load(File.ReadAllText(entry.MusicXmlPath), Score.Composition);
            if (entry.JobId is { } jobId) _ = RenameOnComputerAsync(jobId, cleaned);
            return true;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.Xml.XmlException or FormatException)
        {
            _announcer.Announce(_s.Format("Score_RenameFailed", cleaned), AnnouncementKind.Important);
            return false;
        }
    }

    /// <summary>
    /// First run: "Get started" asks "What do you play?" (when the core has the seats), then Home. The first run is
    /// not shown again, and neither is the question.
    /// </summary>
    [RelayCommand]
    private void GetStarted()
    {
        Settings.FirstRunDone = true;
        if (Seats.IsAvailable && !Settings.SeatChoice.IsSet)
        {
            FirstRunSeat = new SeatPickerViewModel(Seats, _s);
            Screen = Screen.WhatDoYouPlay;
        }
        else Screen = Screen.Start;
    }

    /// <summary>"Continue": the answer is saved now, not while choosing (WCAG 3.2.2).</summary>
    [RelayCommand(CanExecute = nameof(CanContinueWithSeat))]
    private void ContinueWithSeat()
    {
        if (FirstRunSeat?.Choice is not { } choice) return;
        Settings.SeatChoice = choice;
        FirstRunSeat = null;
        Screen = Screen.Start;
    }

    /// <summary>"I conduct or listen": no part is the player's; scores open on every part.</summary>
    [RelayCommand]
    private void ConductOrListen()
    {
        Settings.SeatChoice = SeatChoice.Conductor;
        FirstRunSeat = null;
        Screen = Screen.Start;
    }

    /// <summary>"Not now": nothing is set, the app behaves as before, and the question is not asked again.</summary>
    [RelayCommand]
    private void SkipSeat()
    {
        FirstRunSeat = null;
        Screen = Screen.Start;
    }

    /// <summary>"Check them" on the score, and the end of making a score with notes marked ?.</summary>
    [RelayCommand]
    private void CheckNotes()
    {
        Review.Load();
        if (Review.Items.Count == 0) return;
        Screen = Screen.Review;
    }

    [RelayCommand]
    private void OpenLibraryItem(LibraryItem? item)
    {
        if (item is { OnComputer: true }) { _ = OpenLibraryItemAsync(item); return; }
        if (item is null || Library?.Entries.FirstOrDefault(e => e.Id == item.Id) is not { } entry) return;
        try
        {
            string xml = File.ReadAllText(entry.MusicXmlPath);
            var composition = entry.CompositionPath is { } c && File.Exists(c) ? Core.ParseComposition(File.ReadAllText(c)) : null;
            _result = null;
            _libraryId = entry.Id;
            _myPartOverride = entry.MyPart;
            Output.HasEngineJob = false;
            Output.LayerSource = null;
            Output.IsSoloTake = Lineups.IsSoloTake(composition);
            Output.IsBandTake = Lineups.IsBandTake(composition);
            Output.HasSoloist = Lineups.HasSoloist(composition);
            Output.ShowingSaved(Lineups.Parse(entry.Lineup) ?? Lineups.Recorded(composition), Lineups.RecordedDifficulty(composition), composition);
            Score.Evidence = Library.LoadEvidence(entry);
            Score.Load(xml, composition);
            Score.UseReviewChanges(Library.LoadReviewChanges(entry.Id));
            Screen = Screen.Score;
        }
        catch (Exception e) when (e is IOException or FormatException or System.Xml.XmlException or UnauthorizedAccessException
                                   or System.Text.Json.JsonException or Bridge.CoreBridgeException)
        {
            Start.ErrorText = _s.Format("Start_Error_Score", entry.Title);
            _announcer.Announce(Start.ErrorText, AnnouncementKind.Important);
        }
    }

    [RelayCommand]
    private void NewScore()
    {
        if (!Transcription.IsRunning) Screen = Screen.Start;
    }

    /// <summary>The recorded key and the player's part, for "C major (concert) · D major on your part".</summary>
    private void UpdateOutputContext()
    {
        int mine = Score.MyPartIndex;
        int? chromatic = mine >= 0 && Score.Document is { } doc ? doc.Parts[mine].Transpose.Chromatic : null;
        // Once the player has said what they play, the part is theirs; before, it is the lead's "B♭ instruments".
        Output.SetScoreContext(Score.Composition, chromatic, yours: Settings.SeatChoice.SeatId is not null || _myPartOverride is not null);
    }

    private bool _chooseOutputNext;

    /// <summary>The score on screen has no changed notes: forgotten here and in the library.</summary>
    private void ForgetReviewChanges()
    {
        Score.UseReviewChanges(null);
        if (_libraryId is { } id) Library?.SaveReviewChanges(id, Score.ReviewChanges);
    }

    /// <summary>
    /// A new score: check the notes, then "How should the score be?". A score arranged again with new
    /// choices: its notes to check, then straight to the score (the choice was just made).
    /// </summary>
    private void OpenReviewOrScore(bool rearranged)
    {
        Review.Load();
        _chooseOutputNext = !rearranged && Review.Items.Count > 0;
        Screen = Review.Items.Count > 0 ? Screen.Review : rearranged ? Screen.Score : Screen.ChooseOutput;
    }

    /// <summary>"How should the score be?" from the score's View menu.</summary>
    [RelayCommand]
    private void ChooseOutput() => Screen = Screen.ChooseOutput;

    private void UpdateLibraryCount()
    {
        if (_libraryId is { } id) Keep(() => Library?.SetNotesToCheck(id, Score.UncertainLeft));
    }

    /// <summary>
    /// A write to "Your scores" that must not end what the player is doing: a full disk or a file another
    /// app holds is said (and shown through <see cref="ProblemNoticed"/>), and the score on screen stays as it is.
    /// </summary>
    private void Keep(Action write)
    {
        try { write(); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            string text = _s["Library_SaveFailed"];
            _announcer.Announce(text, AnnouncementKind.Important);
            ProblemNoticed?.Invoke(this, text);
        }
    }

    /// <summary>Something went wrong that the player should see; the window shows it in its notice bar.</summary>
    public event EventHandler<string>? ProblemNoticed;

    /// <summary>"Your scores" has entries (else Home shows the empty state).</summary>
    [ObservableProperty] public partial bool HasLibrary { get; set; }

    private IReadOnlyList<Job> _computerJobs = [];

    /// <summary>Fetches the computer's finished scores; keeps this PC's list when the computer can't be reached.</summary>
    public async Task RefreshComputerScoresAsync()
    {
        try
        {
            _computerJobs = await Engine.ListJobsAsync();
        }
        catch (Exception e) when (e is EngineException or NotSupportedException or HttpRequestException or TaskCanceledException
                                   or System.Text.Json.JsonException)
        {
            _computerJobs = [];
        }
        RefreshLibrary();
    }

    /// <summary>Opens any row: a computer score is downloaded into the library first. <paramref name="review"/> goes to "Check the notes".</summary>
    public async Task OpenLibraryItemAsync(LibraryItem item, bool review = false)
    {
        if (item.OnComputer && item.JobId is { } jobId)
        {
            try
            {
                var job = await Engine.GetJobAsync(jobId);
                var composition = await Engine.GetCompositionAsync(jobId);
                string xml;
                await using (var stream = await Engine.DownloadAsync(jobId, JobDownload.MusicXml))
                using (var reader = new StreamReader(stream))
                    xml = await reader.ReadToEndAsync();
                Evidence? evidence = null;
                try { evidence = await Engine.GetEvidenceAsync(jobId); }
                catch (Exception e) when (e is EngineException or NotSupportedException or System.Text.Json.JsonException) { }
                _result = null;
                _myPartOverride = Library?.Entries.FirstOrDefault(e => e.JobId == jobId)?.MyPart;
                Output.HasEngineJob = false;
                Output.LayerSource = null;
                Output.IsSoloTake = Lineups.IsSoloTake(composition, job.Profile);
                Output.IsBandTake = Lineups.IsBandTake(composition, job.Profile);
                Output.HasSoloist = Lineups.HasSoloist(composition, job.Profile);
                Output.ShowingSaved(Lineups.Recorded(composition), Lineups.RecordedDifficulty(composition), composition);
                Score.Evidence = evidence;
                Score.Load(xml, composition);
                _libraryId = Library?.AddMade(job.Title ?? item.Title, xml, composition, Score.Parts.Count, Score.Player.BarCount,
                    Score.UncertainLeft, jobId, evidence, Lineups.Recorded(composition) is { } recorded ? Lineups.Engine(recorded) : null).Id;
                // The engine's score replaces the saved one, without the notes changed here.
                ForgetReviewChanges();
                Screen = Screen.Score;
            }
            catch (Exception e) when (e is EngineException or HttpRequestException or IOException or FormatException
                                       or System.Xml.XmlException or System.Text.Json.JsonException or Bridge.CoreBridgeException)
            {
                Start.ErrorText = _s.Format("Start_Error_Score", item.Title);
                _announcer.Announce(Start.ErrorText, AnnouncementKind.Important);
                return;
            }
        }
        else OpenLibraryItem(item);
        if (review && Screen == Screen.Score) CheckNotes();
    }

    /// <summary>"Edit title" on any row; a score from the computer is renamed there too.</summary>
    public async Task<bool> RenameLibraryItemAsync(LibraryItem item, string title)
    {
        string cleaned = title.Trim();
        if (cleaned.Length == 0) return false;
        if (item.OnComputer)
        {
            if (item.JobId is not { } jobId || !await RenameOnComputerAsync(jobId, cleaned)) return false;
            await RefreshComputerScoresAsync();
            return true;
        }
        if (_libraryId == item.Id) return RenameCurrentScore(cleaned);
        if (Library?.Entries.FirstOrDefault(e => e.Id == item.Id) is not { } entry) return false;
        try
        {
            Library.Rename(item.Id, cleaned);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.Xml.XmlException or FormatException)
        {
            _announcer.Announce(_s.Format("Score_RenameFailed", cleaned), AnnouncementKind.Important);
            return false;
        }
        if (entry.JobId is { } job) _ = RenameOnComputerAsync(job, cleaned);
        return true;
    }

    /// <summary>"Delete" on any row: this PC's copy, or the run on the computer.</summary>
    public async Task<bool> DeleteLibraryItemAsync(LibraryItem item)
    {
        if (item.OnComputer)
        {
            try
            {
                if (item.JobId is { } jobId) await Engine.DeleteRunAsync(jobId);
            }
            catch (Exception e) when (e is EngineException or NotSupportedException or HttpRequestException)
            {
                _announcer.Announce(_s.Format("Library_DeleteFailed", item.Title), AnnouncementKind.Important);
                return false;
            }
            await RefreshComputerScoresAsync();
        }
        else
        {
            Keep(() => Library?.Remove(item.Id));
            if (_libraryId == item.Id)
            {
                _libraryId = null;
                if (Screen is Screen.Score or Screen.Review or Screen.ChooseOutput) Screen = Screen.Start;
            }
        }
        _announcer.Announce(_s.Format("Library_Deleted", item.Title));
        return true;
    }

    private async Task<bool> RenameOnComputerAsync(string jobId, string title)
    {
        try
        {
            await Engine.RenameRunAsync(jobId, title);
            return true;
        }
        catch (Exception e) when (e is EngineException or NotSupportedException or HttpRequestException)
        {
            return false;
        }
    }

    private void RefreshLibrary()
    {
        LibraryItems.Clear();
        var rows = new List<(DateTimeOffset When, LibraryItem Item)>();
        if (Library is not null)
            rows.AddRange(Library.Entries.Select(e => (e.Updated, new LibraryItem(e.Id, ScoreTitles.Display(e.Title, e.Updated, _s), LibrarySubtitle(e)))));
        // The computer's finished runs not already here; re-runs of one recording collapse to the latest.
        var downloaded = Library?.Entries.Select(e => e.JobId).OfType<string>().ToHashSet() ?? [];
        var seenAudio = new HashSet<string>();
        foreach (var j in _computerJobs.OrderByDescending(j => j.Created))
        {
            if (j.Status != JobStatus.Succeeded || !(j.Outputs ?? []).Any(o => o.EndsWith(".musicxml", StringComparison.OrdinalIgnoreCase))) continue;
            if (j.AudioId is { } audio && !seenAudio.Add(audio)) continue;
            if (downloaded.Contains(j.Id)) continue;
            var when = DateTimeOffset.FromUnixTimeMilliseconds((long)(j.Created * 1000)).ToLocalTime();
            rows.Add((when, new LibraryItem("job:" + j.Id, ScoreTitles.Display(j.Title, when, _s), _s.Format("Library_OnComputer", WhenText(when)), true, j.Id)));
        }
        MarkDuplicateTimes(rows);
        foreach (var (_, item) in rows.OrderByDescending(r => r.When).Take(20)) LibraryItems.Add(item);
        HasLibrary = LibraryItems.Count > 0;
    }

    private string WhenText(DateTimeOffset when) => when.Date == DateTimeOffset.Now.Date ? _s["Library_Today"]
        : when.Date == DateTimeOffset.Now.Date.AddDays(-1) ? _s["Library_Yesterday"]
        : when.ToString(_s.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase) ? "d. MMMM" : "d MMM", System.Globalization.CultureInfo.CurrentUICulture);

    /// <summary>Same titles get the time as well ("Today 19:02"), so the recordings can be told apart.</summary>
    private void MarkDuplicateTimes(List<(DateTimeOffset When, LibraryItem Item)> rows)
    {
        var dupes = ScoreTitles.Duplicates(rows.Select(r => r.Item.Title));
        for (int i = 0; i < rows.Count; i++)
            if (dupes.Contains(rows[i].Item.Title))
                rows[i] = (rows[i].When, rows[i].Item with
                {
                    Subtitle = rows[i].Item.Subtitle.Replace(WhenText(rows[i].When),
                        WhenText(rows[i].When) + " " + rows[i].When.ToLocalTime().ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture)),
                });
    }

    /// <summary>
    /// "Full band", "Small band" or "Quartet" from the lineup the score was arranged for; the part
    /// count only when that is not known (a score file opened as it is).
    /// </summary>
    public string LineupLabel(Lineup? lineup, int parts) => (parts, lineup) switch
    {
        ( <= 1, _) => _s["Library_OnePart"],
        (_, Lineup.Quartet) => _s["Library_Quartet"],
        (_, Lineup.MinimalBand) => _s["Library_SmallBand"],
        (_, Lineup.FullBand) => _s["Library_FullBand"],
        ( <= 6, null) => _s["Library_SmallBand"],
        (_, null) => _s["Library_FullBand"],
        _ => throw new ArgumentOutOfRangeException(nameof(lineup), lineup, null),
    };

    /// <summary>The lineup of the score being shown: what it was arranged with, or its parts when it came as a file.</summary>
    public Lineup? ShownLineup =>
        Score.Composition is not null ? Output.AppliedLineup
        : Score.Document is { } doc && Lineups.IsQuartet(doc.Parts.Select(p => p.Name)) ? Lineup.Quartet
        : null;

    /// <summary>"Quartet · 32 bars" under the score's title.</summary>
    public string ScoreSubtitle => _s.Format("Title_ScoreSubtitle", LineupLabel(ShownLineup, Score.Parts.Count), Score.Player.BarCount);

    private string LibrarySubtitle(LibraryEntry e)
    {
        if (!e.IsAvailable) return _s["Library_Unavailable"];
        string lineup = LineupLabel(Lineups.Parse(e.Lineup), e.Parts);
        string check = e.NotesToCheck > 0 ? " · " + _s.Format(e.NotesToCheck == 1 ? "Library_ToCheckOne" : "Library_ToCheck", e.NotesToCheck) : "";
        return _s.Format("Library_Subtitle", lineup, e.Bars, WhenText(e.Updated)) + check;
    }

    public IEngineClient Engine => _engine ??= _engineFactory(Settings.EngineUri, Settings.EngineToken);

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(OpenExportCommand), nameof(BackCommand))]
    public partial Screen Screen { get; set; } = Screen.Start;

    partial void OnScreenChanged(Screen value)
    {
        // Leaving a screen stops "Listen to this bar" and closes the music stand.
        Score.StopListening(announce: false);
        if (value != Screen.Score) Score.Stand.Leave(announce: false);
        _announcer.Announce(_s[$"Screen_{value}"], AnnouncementKind.Status);
    }

    public void OpenScoreFile(string path)
    {
        try
        {
            string xml = File.ReadAllText(path);
            _result = null;
            _myPartOverride = Library?.Entries.FirstOrDefault(e => string.Equals(e.MusicXmlPath, path, StringComparison.OrdinalIgnoreCase))?.MyPart;
            Output.HasEngineJob = false;
            Output.LayerSource = null;
            Output.IsSoloTake = false;
            Output.IsBandTake = false;
            Output.HasSoloist = false;
            Score.Evidence = null;
            Score.Load(xml, null);
            _libraryId = Library?.AddOpened(path, Score.Title is { Length: > 0 } t ? t : Path.GetFileNameWithoutExtension(path),
                Score.Parts.Count, Score.Player.BarCount, Score.UncertainLeft).Id;
            Score.UseReviewChanges(null);
            Screen = Screen.Score;
        }
        catch (Exception e) when (e is IOException or FormatException or System.Xml.XmlException or UnauthorizedAccessException)
        {
            Start.ErrorText = _s.Format("Start_Error_Score", Path.GetFileName(path));
            _announcer.Announce(Start.ErrorText, AnnouncementKind.Important);
        }
    }

    [RelayCommand(CanExecute = nameof(IsOnScore))]
    private void OpenExport() =>
        Export.Prepare(Score, Score.Player.Player as AlphaTabScorePlayer, _result is null ? null : Engine, _result?.JobId, _result?.Outputs, ShownLineup);

    private bool IsOnScore() => Screen == Screen.Score;

    [RelayCommand(CanExecute = nameof(CanGoBack))]
    private void Back()
    {
        Screen = Screen switch
        {
            Screen.SourceKind => Screen.Start,
            // After a failure: back to the score being re-arranged, or to the choice with the source kept.
            Screen.Transcribing => _result is not null ? Screen.Score : Screen.SourceKind,
            // The music stand closes first; the part view goes back to the full score; the full score goes Home.
            Screen.Score when Score.Stand.IsOpen => LeaveStand(),
            Screen.Score when Score.SelectedPartIndex >= 0 => BackToFullScore(),
            Screen.Score => Screen.Start,
            Screen.Review => Screen.Score,
            Screen.ChooseOutput => Screen.Score,
            Screen.Error => Screen.Start,
            _ => Screen,
        };
    }

    private Screen LeaveStand()
    {
        Score.Stand.Leave();
        return Screen.Score;
    }

    /// <summary>Library → Open on the music stand: the score, then the stand, in one step.</summary>
    public async Task OpenOnMusicStandAsync(LibraryItem item)
    {
        await OpenLibraryItemAsync(item);
        if (Screen == Screen.Score && Score.IsLoaded) Score.Stand.Enter();
    }

    private Screen BackToFullScore()
    {
        Score.SelectedPartIndex = -1;
        return Screen.Score;
    }

    /// <summary>Back works everywhere except while a transcription runs (Cancel is the way out then).</summary>
    private bool CanGoBack() => Screen is Screen.SourceKind or Screen.Score or Screen.Review or Screen.Error or Screen.ChooseOutput
                                || Screen == Screen.Transcribing && !Transcription.IsRunning;

    /// <summary>For tests: the last transcription result.</summary>
    public TranscriptionResult? LastResult => _result;

    public Composition? Composition => Score.Composition;
}
