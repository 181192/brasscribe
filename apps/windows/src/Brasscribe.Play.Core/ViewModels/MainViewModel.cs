using Brasscribe.Play.Core.Arrangement;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>The screens of the Play flow (design/system.md §3). The part view is the score screen with one part chosen.</summary>
public enum Screen { Start, SourceKind, Transcribing, Score, FirstRun, Review, Error, ChooseOutput }

/// <summary>
/// The flow of the app: start (import or record) → "What is this?" → transcription → score.
/// Owns the child view models and the engine client; the WinUI shell binds <see cref="Screen"/> to
/// its navigation and moves keyboard focus to each screen's heading.
/// </summary>
/// <summary>A row of "Your scores".</summary>
public sealed record LibraryItem(string Id, string Title, string Subtitle);

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
        Error = new ErrorViewModel(strings);
        Library = library;
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
        Error.Retry += async (_, _) =>
        {
            if (_lastChoice is { } choice)
            {
                Screen = Screen.Transcribing;
                await Transcription.RunAsync(choice.Source, choice.Kind, Output.Options);
            }
            else Screen = Screen.Start;
        };
        Error.Alternative += (_, _) => Screen = Screen.Start;
        Transcription.FailedWith += (_, failure) =>
        {
            Error.Show(failure == TranscriptionFailure.ComputerUnreachable ? ErrorKind.ComputerUnreachable : ErrorKind.ScoreFailed,
                Transcription.ErrorText);
            Screen = Screen.Error;
        };

        Start.SourceReady += async (_, src) =>
        {
            Kind.Source = src;
            Kind.Selected = null;
            Kind.SetWhere(Settings.EngineUri);
            Screen = Screen.SourceKind;
            await Kind.RefreshFromEngineAsync(Engine);
        };
        Start.ScoreOpened += (_, path) => OpenScoreFile(path);
        Kind.Chosen += async (_, choice) =>
        {
            _lastChoice = choice;
            _result = null;
            Screen = Screen.Transcribing;
            await Transcription.RunAsync(choice.Source, choice.Kind, Output.Options);
            if (!Transcription.IsRunning && _result is null && Screen == Screen.Transcribing && Transcription.ErrorText is null)
                Screen = Screen.SourceKind; // cancelled: back to the choice, source kept
        };
        Transcription.Completed += (_, r) =>
        {
            _result = r;
            Output.HasEngineJob = r.AudioId is not null;
            Output.Applied = r.Options ?? ArrangementOptions.Default;
            Output.Title = r.Composition.Title;
            Output.LayerSource = r.JobId is { Length: > 0 } jobId && LayerCacheRoot is { } cache
                ? ct => EngineLayerSource.LoadAsync(Engine, jobId, cache, ct)
                : null;
            Score.Original?.Open(r.Source.OriginalPath ?? r.Source.WavPath, r.Source.HasVideo);
            Score.Load(r.MusicXml, r.Composition);
            _libraryId = Library?.AddMade(Score.Title is { Length: > 0 } t ? t : r.Source.DisplayName, r.MusicXml, r.Composition,
                Score.Parts.Count, Score.Player.BarCount, Score.UncertainLeft, r.JobId).Id;
            OpenReviewOrScore();
        };
        Transcription.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(TranscriptionViewModel.IsRunning)) BackCommand.NotifyCanExecuteChanged();
        };
        Output.Arranged += (_, xml) =>
        {
            Score.Load(xml, Score.Composition);
            Screen = Screen.Score;
        };
        Output.ArrangedBand += (_, band) =>
        {
            Score.Load(band.MusicXml, core.ParseComposition(band.CompositionJson));
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
        };
        Score.SingleKeyShortcuts = Settings.SingleKeyShortcuts;
        Score.Verbosity = Settings.Verbosity;
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
    public ErrorViewModel Error { get; }
    public ScoreLibrary? Library { get; }

    /// <summary>"Your scores" in the sidebar and on Home, newest first.</summary>
    public System.Collections.ObjectModel.ObservableCollection<LibraryItem> LibraryItems { get; } = [];

    private (SourceAudio Source, SourceKindOption Kind)? _lastChoice;
    private string? _libraryId;

    /// <summary>First run: "Get started" goes Home and the screen is not shown again.</summary>
    [RelayCommand]
    private void GetStarted()
    {
        Settings.FirstRunDone = true;
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
        if (item is null || Library?.Entries.FirstOrDefault(e => e.Id == item.Id) is not { } entry) return;
        try
        {
            string xml = File.ReadAllText(entry.MusicXmlPath);
            var composition = entry.CompositionPath is { } c && File.Exists(c) ? Core.ParseComposition(File.ReadAllText(c)) : null;
            _result = null;
            _libraryId = entry.Id;
            Output.HasEngineJob = false;
            Output.LayerSource = null;
            Score.Load(xml, composition);
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

    private bool _chooseOutputNext;

    private void OpenReviewOrScore()
    {
        Review.Load();
        _chooseOutputNext = Review.Items.Count > 0;
        Screen = Review.Items.Count > 0 ? Screen.Review : Screen.ChooseOutput;
    }

    /// <summary>"How should the score be?" from the score's View menu.</summary>
    [RelayCommand]
    private void ChooseOutput() => Screen = Screen.ChooseOutput;

    private void UpdateLibraryCount()
    {
        if (_libraryId is { } id) Library?.SetNotesToCheck(id, Score.UncertainLeft);
    }

    /// <summary>"Your scores" has entries (else Home shows the empty state).</summary>
    [ObservableProperty] public partial bool HasLibrary { get; set; }

    private void RefreshLibrary()
    {
        LibraryItems.Clear();
        HasLibrary = Library is { Entries.Count: > 0 };
        if (Library is null) return;
        foreach (var e in Library.Entries.Take(20))
            LibraryItems.Add(new LibraryItem(e.Id, e.Title, LibrarySubtitle(e)));
    }

    private string LibrarySubtitle(LibraryEntry e)
    {
        string lineup = _s[e.Parts <= 1 ? "Library_OnePart" : e.Parts <= 6 ? "Library_SmallBand" : "Library_FullBand"];
        string when = e.Updated.Date == DateTimeOffset.Now.Date ? _s["Library_Today"]
            : e.Updated.ToString(_s.Language.StartsWith("nb", StringComparison.OrdinalIgnoreCase) ? "d. MMMM" : "d MMM", System.Globalization.CultureInfo.CurrentUICulture);
        string check = e.NotesToCheck > 0 ? " · " + _s.Format("Library_ToCheck", e.NotesToCheck) : "";
        return _s.Format("Library_Subtitle", lineup, e.Bars, when) + check;
    }

    public IEngineClient Engine => _engine ??= _engineFactory(Settings.EngineUri, Settings.EngineToken);

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(OpenExportCommand), nameof(BackCommand))]
    public partial Screen Screen { get; set; } = Screen.Start;

    partial void OnScreenChanged(Screen value) =>
        _announcer.Announce(_s[$"Screen_{value}"], AnnouncementKind.Status);

    public void OpenScoreFile(string path)
    {
        try
        {
            string xml = File.ReadAllText(path);
            _result = null;
            Output.HasEngineJob = false;
            Output.LayerSource = null;
            Score.Load(xml, null);
            _libraryId = Library?.AddOpened(path, Score.Title is { Length: > 0 } t ? t : Path.GetFileNameWithoutExtension(path),
                Score.Parts.Count, Score.Player.BarCount, Score.UncertainLeft).Id;
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
        Export.Prepare(Score, Score.Player.Player as AlphaTabScorePlayer, _result is null ? null : Engine, _result?.JobId, _result?.Outputs);

    private bool IsOnScore() => Screen == Screen.Score;

    [RelayCommand(CanExecute = nameof(CanGoBack))]
    private void Back()
    {
        Screen = Screen switch
        {
            Screen.SourceKind => Screen.Start,
            // After a failure: back to the score being re-arranged, or to the choice with the source kept.
            Screen.Transcribing => _result is not null ? Screen.Score : Screen.SourceKind,
            // The part view goes back to the full score; the full score goes Home.
            Screen.Score when Score.SelectedPartIndex >= 0 => BackToFullScore(),
            Screen.Score => Screen.Start,
            Screen.Review => Screen.Score,
            Screen.ChooseOutput => Screen.Score,
            Screen.Error => Screen.Start,
            _ => Screen,
        };
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
