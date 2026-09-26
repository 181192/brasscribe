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

public enum Screen { Start, SourceKind, Transcribing, Score }

/// <summary>
/// The flow of the app: start (import or record) → "What is this?" → transcription → score.
/// Owns the child view models and the engine client; the WinUI shell binds <see cref="Screen"/> to
/// its navigation and moves keyboard focus to each screen's heading.
/// </summary>
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
        Func<Uri, string?, IEngineClient> engineFactory, IAnnouncer announcer, IStrings strings, ICoreBridge core)
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

        Start.SourceReady += async (_, src) =>
        {
            Kind.Source = src;
            Kind.Selected = null;
            Screen = Screen.SourceKind;
            await Kind.RefreshFromEngineAsync(Engine);
        };
        Start.ScoreOpened += (_, path) => OpenScoreFile(path);
        Kind.Chosen += async (_, choice) =>
        {
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
            Output.Title = r.Composition.Title;
            Output.LayerSource = r.JobId is { Length: > 0 } jobId && LayerCacheRoot is { } cache
                ? ct => EngineLayerSource.LoadAsync(Engine, jobId, cache, ct)
                : null;
            Score.Original?.Open(r.Source.OriginalPath ?? r.Source.WavPath, r.Source.HasVideo);
            Score.Load(r.MusicXml, r.Composition);
            Screen = Screen.Score;
        };
        Transcription.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(TranscriptionViewModel.IsRunning)) BackCommand.NotifyCanExecuteChanged();
        };
        Output.Arranged += (_, xml) => Score.Load(xml, Score.Composition);
        Output.ArrangedBand += (_, band) => Score.Load(band.MusicXml, core.ParseComposition(band.CompositionJson));
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
            Screen.Score => Screen.Start,
            _ => Screen,
        };
    }

    /// <summary>Back works everywhere except while a transcription runs (Cancel is the way out then).</summary>
    private bool CanGoBack() => Screen is Screen.SourceKind or Screen.Score || Screen == Screen.Transcribing && !Transcription.IsRunning;

    /// <summary>For tests: the last transcription result.</summary>
    public TranscriptionResult? LastResult => _result;

    public Composition? Composition => Score.Composition;
}
