using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;
using Kalli.Scribe.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Kalli.Scribe.ViewModels;

/// <summary>One plain-language step of making a score, as the transcribing screen lists it.</summary>
public sealed partial class TranscriptionStep(string key, string label) : ObservableObject
{
    public string Key { get; } = key;
    public string Label { get; } = label;
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsPending))]
    public partial bool IsDone { get; set; }
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(IsPending))]
    public partial bool IsCurrent { get; set; }
    public bool IsPending => !IsDone && !IsCurrent;
    [ObservableProperty] public partial string AccessibleName { get; set; } = label;
}

/// <summary>Why making a score stopped, so the error screen can say what to do next.</summary>
public enum TranscriptionFailure { None, ComputerUnreachable, Failed, RecordingUnreadable, UpdateApp, UpdateBandroom }

/// <summary>A finished transcription.</summary>
public sealed record TranscriptionResult(string JobId, Composition Composition, string MusicXml, IReadOnlyList<string> Outputs, SourceAudio Source,
    string? AudioId = null, string? Profile = null, ArrangementOptions? Options = null, Evidence? Evidence = null);

/// <summary>
/// Runs a transcription on the companion engine: upload, job, live progress in plain language with
/// an estimated time left, and cancel. Progress announcements are throttled so a screen reader is
/// not flooded; completion and failure are always announced.
/// </summary>
public sealed partial class TranscriptionViewModel : ObservableObject
{
    private static readonly TimeSpan AnnounceEvery = TimeSpan.FromSeconds(10);

    private readonly Func<IEngineClient> _engine;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private readonly IUiDispatcher _ui;
    private readonly TimeProvider _clock;
    private CancellationTokenSource? _cts;
    private string? _jobId;
    private long _lastAnnounce;
    private double _lastAnnouncedPercent;

    public TranscriptionViewModel(Func<IEngineClient> engine, IAnnouncer announcer, IStrings strings, IUiDispatcher ui, TimeProvider? clock = null)
    {
        _engine = engine;
        _announcer = announcer;
        _s = strings;
        _ui = ui;
        _clock = clock ?? TimeProvider.System;
    }

    public event EventHandler<TranscriptionResult>? Completed;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(CancelCommand))]
    public partial bool IsRunning { get; set; }

    /// <summary>0 to 100 for the progress bar.</summary>
    [ObservableProperty] public partial double Percent { get; set; }
    [ObservableProperty] public partial string StageText { get; set; } = "";
    [ObservableProperty] public partial string EtaText { get; set; } = "";
    [ObservableProperty] public partial string? ErrorText { get; set; }

    /// <summary>The engine's own words for the failure, for the error screen's technical details only.</summary>
    public string? ErrorDetail { get; private set; }
    [ObservableProperty] public partial string Title { get; set; } = "";
    [ObservableProperty] public partial string? DeviceText { get; set; }

    /// <summary>The plain-language steps of the running profile (design/brands/brasscribe/system.md §5, Progress with steps).</summary>
    public System.Collections.ObjectModel.ObservableCollection<TranscriptionStep> Steps { get; } = [];

    /// <summary>"STEP 4 OF 6 · SOLOIST WITH ORCHESTRA OR BAND".</summary>
    [ObservableProperty] public partial string Overline { get; set; } = "";

    /// <summary>The current step in plain words, the screen's heading.</summary>
    [ObservableProperty] public partial string StepHeading { get; set; } = "";

    [ObservableProperty] public partial string PercentText { get; set; } = "";

    /// <summary>True while "Stop making this score?" is asked.</summary>
    [ObservableProperty] public partial bool IsConfirmingCancel { get; set; }

    [ObservableProperty] public partial TranscriptionFailure Failure { get; set; }

    /// <summary>Raised when making the score stopped with an error the error screen explains.</summary>
    public event EventHandler<TranscriptionFailure>? FailedWith;

    private string _kindLabel = "";

    /// <summary>The steps a profile goes through, in order.</summary>
    public static IReadOnlyList<string> StepKeys(string profile) => profile switch
    {
        "solo" => ["Ready", "Beats", "Notes", "Arrange", "Layout"],
        _ => ["Ready", "Beats", "Separate", "Notes", "Arrange", "Layout"],
    };

    /// <summary>The step an engine stage belongs to.</summary>
    public static string StepOf(string stage) => stage.Split('.')[0] switch
    {
        "separate" or "stems" or "layers" or "separation" => "Separate",
        "beats" or "beat" => "Beats",
        "transcribe" or "contour" or "f0" or "solo" or "vote" => "Notes",
        "arrange" => "Arrange",
        "export" or "render" or "musicxml" => "Layout",
        _ => "",
    };

    private void ResetSteps(string profile, string kindLabel)
    {
        _kindLabel = kindLabel;
        Steps.Clear();
        foreach (var key in StepKeys(profile))
            Steps.Add(new TranscriptionStep(key, _s[key == "Separate" && profile == "orchestra-with-soloist" ? "Transcribe_Step_SeparateSoloist" : $"Transcribe_Step_{key}"]));
        SetStep("Ready");
    }

    private void SetStep(string key)
    {
        int index = Steps.ToList().FindIndex(x => x.Key == key);
        if (index < 0) return;
        for (int i = 0; i < Steps.Count; i++)
        {
            Steps[i].IsDone = i < index;
            Steps[i].IsCurrent = i == index;
            Steps[i].AccessibleName = _s.Format(i < index ? "Transcribe_StepDone" : i == index ? "Transcribe_StepCurrent" : "Transcribe_StepPending", Steps[i].Label);
        }
        StepHeading = Steps[index].Label;
        Overline = _s.Format("Transcribe_Overline", index + 1, Steps.Count, _kindLabel).ToUpperInvariant();
    }

    /// <summary>Shows a run at one step without an engine (the screenshot scenes).</summary>
    public void ShowProgress(string title, string profile, string kindLabel, string step, double percent, TimeSpan? left)
    {
        Title = title;
        ResetSteps(profile, kindLabel);
        SetStep(step);
        Percent = percent;
        EtaText = left is { } l ? EtaPhrase(l) : _s["Transcribe_Eta_Unknown"];
    }

    partial void OnPercentChanged(double value) => PercentText = Screens.Percent(value, _s.Language);

    /// <summary>Uploads the source and transcribes it with the chosen profile and arrangement options.</summary>
    public Task RunAsync(SourceAudio source, SourceKindOption kind, ArrangementOptions? options = null) =>
        RunJobAsync(source, kind.Label, kind.Profile, options ?? ArrangementOptions.Default, audioId: null);

    /// <summary>
    /// Uploads the source, unless the computer already has it (<paramref name="audioId"/>), and runs the job the app
    /// makes of the upload (<paramref name="job"/> takes its id): the profile's options are the app's.
    /// </summary>
    public Task RunAsync(SourceAudio source, string kindLabel, string profile, Func<string, JobCreate> job, string? audioId = null) =>
        RunJobAsync(source, kindLabel, profile, job, options: null, audioId);

    /// <summary>
    /// Arranges an earlier transcription again with other options (lineup, difficulty, key). The engine
    /// caches every stage by content, so only the arrangement and its exports run again.
    /// </summary>
    public Task RearrangeAsync(TranscriptionResult previous, ArrangementOptions options) =>
        RunJobAsync(previous.Source, previous.Profile ?? "orchestra-with-soloist", previous.Profile ?? "", options, previous.AudioId);

    private Task RunJobAsync(SourceAudio source, string kindLabel, string profile, ArrangementOptions options, string? audioId) =>
        RunJobAsync(source, kindLabel, profile, uploaded => new JobCreate(uploaded, profile, RenderAudio: true,
            Title: Path.GetFileNameWithoutExtension(source.DisplayName),
            Lineup: options.Lineup, Difficulty: options.Difficulty, Key: options.Key, Transpose: options.Transpose,
            Seat: options.Seat, Reads: options.Reads, Lead: options.Lead), options, audioId);

    private async Task RunJobAsync(SourceAudio source, string kindLabel, string profile, Func<string, JobCreate> request,
        ArrangementOptions? options, string? audioId)
    {
        _cts?.Cancel();
        _cts = new CancellationTokenSource();
        var ct = _cts.Token;
        var engine = _engine();
        var estimator = new ProgressEstimator(_clock);
        IsRunning = true;
        ErrorText = null;
        ErrorDetail = null;
        Failure = TranscriptionFailure.None;
        IsConfirmingCancel = false;
        ResetSteps(profile, kindLabel);
        Percent = 0;
        Title = source.DisplayName;
        StageText = _s["Transcribe_Stage_Upload"];
        EtaText = _s["Transcribe_Eta_Unknown"];
        _announcer.Announce(audioId is null
            ? _s.Format("Transcribe_Started", source.DisplayName, kindLabel)
            : _s["Transcribe_Rearranging"], AnnouncementKind.Important);
        try
        {
            var health = await engine.GetHealthAsync(ct);
            // Another interface version: nothing is uploaded and no job is sent.
            var match = InterfaceMatch.Of(health.InterfaceVersion);
            if (match != InterfaceAnswer.Same)
            {
                StopForUpdate(match, InterfaceMatch.Details(health.InterfaceVersion));
                return;
            }
            DeviceText = _s.Format("Transcribe_Device", health.Device.ToUpperInvariant());

            if (audioId is null)
            {
                await using var file = OpenRecording(source.WavPath);
                audioId = (await engine.UploadAudioAsync(file, Path.GetFileName(source.WavPath), ct)).AudioId;
            }

            var job = await engine.CreateJobAsync(request(audioId), ct);
            _jobId = job.Id;
            estimator.Start();

            await foreach (var ev in engine.StreamEventsAsync(job.Id, ct: ct))
            {
                if (ev.Type == "stage")
                {
                    if (ev.Stage is { } stage && ev.Status == "started")
                    {
                        StageText = StageName(stage);
                        if (StepOf(stage) is { Length: > 0 } step) _ui.Post(() => SetStep(step));
                    }
                    if (ev.Device is { } device) DeviceText = _s.Format("Transcribe_Device", device.ToUpperInvariant());
                    if (ev.Fraction is { } f) Update(estimator, f);
                }
                else if (ev.Type == "job" && ev.Status is { } status)
                {
                    if (status == JobStatus.Failed) throw new EngineException(ev.Error ?? "job failed", code: EngineException.JobFailed);
                    if (status == JobStatus.Cancelled) throw new OperationCanceledException();
                }
            }

            job = await engine.GetJobAsync(job.Id, ct);
            if (job.Status != JobStatus.Succeeded) throw new EngineException(job.Error ?? "job failed", code: EngineException.JobFailed);
            var composition = await engine.GetCompositionAsync(job.Id, ct);
            string xml;
            await using (var s = await engine.DownloadAsync(job.Id, JobDownload.MusicXml, ct))
            using (var reader = new StreamReader(s))
                xml = await reader.ReadToEndAsync(ct);

            Percent = 100;
            foreach (var st in Steps) { st.IsDone = true; st.IsCurrent = false; }
            StageText = _s["Transcribe_Done"];
            EtaText = "";
            Evidence? evidence = null;
            try { evidence = await engine.GetEvidenceAsync(job.Id, ct); }
            catch (Exception e) when (e is EngineException or NotSupportedException or System.Text.Json.JsonException) { }
            _announcer.Announce(_s["Transcribe_Done"], AnnouncementKind.Important);
            Completed?.Invoke(this, new TranscriptionResult(job.Id, composition, xml, job.Outputs ?? [], source, audioId, profile, options, evidence));
        }
        catch (OperationCanceledException e) when (!ct.IsCancellationRequested && e.InnerException is TimeoutException)
        {
            // Not the player's Cancel: a request timed out (HttpClient throws a cancellation for that).
            Fail(new EngineException("the request timed out", null, e, EngineException.Timeout));
        }
        catch (OperationCanceledException)
        {
            StageText = _s["Transcribe_Cancelled"];
            _announcer.Announce(StageText, AnnouncementKind.Important);
        }
        catch (EngineException e) when (e.Interface is { } answer)
        {
            // Found after the start (the engine was replaced while the job ran): the client sent it nothing more.
            StopForUpdate(answer, e.Message);
        }
        catch (EngineException e)
        {
            Fail(e);
        }
        catch (UnreadableRecordingException e)
        {
            // The recording on this PC was moved, deleted or is locked by another app: nothing was sent.
            ErrorText = _s["Error_RecordingUnreadable_Title"];
            ErrorDetail = e.InnerException?.Message;
            Failure = TranscriptionFailure.RecordingUnreadable;
            _announcer.Announce(_s.Format("Transcribe_Error", ErrorText), AnnouncementKind.Important);
            FailedWith?.Invoke(this, Failure);
        }
        catch (IOException e)
        {
            // The connection broke off while a download was read.
            Fail(new EngineException("The connection to the engine broke off.", null, e));
        }
        finally
        {
            IsRunning = false;
            _jobId = null;
        }
    }

    private sealed class UnreadableRecordingException(Exception inner) : Exception(inner.Message, inner);

    private static FileStream OpenRecording(string path)
    {
        try { return File.OpenRead(path); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { throw new UnreadableRecordingException(e); }
    }

    /// <summary>
    /// Says what went wrong in the app's own words (EngineErrors), never the engine's English detail.
    /// No HTTP status and no code means the request never got an answer: the computer is off, asleep or elsewhere.
    /// </summary>
    private void Fail(EngineException e)
    {
        ErrorText = EngineErrors.Message(e, _s);
        ErrorDetail = e.Message;
        Failure = e.Status is null && e.Code is null ? TranscriptionFailure.ComputerUnreachable : TranscriptionFailure.Failed;
        _announcer.Announce(_s.Format("Transcribe_Error", ErrorText), AnnouncementKind.Important);
        FailedWith?.Invoke(this, Failure);
    }

    /// <summary>
    /// The app and the engine have different interface versions: says which of the two to update. The numbers
    /// (<paramref name="details"/>) are for the error screen's technical details only.
    /// </summary>
    private void StopForUpdate(InterfaceAnswer match, string details)
    {
        bool app = match == InterfaceAnswer.UpdateApp;
        ErrorText = _s[app ? "Error_UpdateApp_Title" : "Error_UpdateBandroom_Title"];
        ErrorDetail = details;
        Failure = app ? TranscriptionFailure.UpdateApp : TranscriptionFailure.UpdateBandroom;
        _announcer.Announce(_s.Format("Transcribe_Error", ErrorText), AnnouncementKind.Important);
        FailedWith?.Invoke(this, Failure);
    }

    /// <summary>Cancel asks first: stopping throws away the minutes spent so far (the recording stays).</summary>
    [RelayCommand(CanExecute = nameof(IsRunning))]
    private void AskCancel()
    {
        IsConfirmingCancel = true;
        _announcer.Announce(_s["Transcribe_CancelConfirm"], AnnouncementKind.Important);
    }

    [RelayCommand]
    private void KeepGoing() => IsConfirmingCancel = false;

    [RelayCommand(CanExecute = nameof(IsRunning))]
    private async Task CancelAsync()
    {
        IsConfirmingCancel = false;
        var id = _jobId;
        _cts?.Cancel();
        if (id is not null)
        {
            try { await _engine().CancelJobAsync(id); }
            catch (EngineException) { /* the job may already have ended */ }
        }
    }

    private void Update(ProgressEstimator estimator, double fraction)
    {
        var remaining = estimator.Update(fraction);
        _ui.Post(() =>
        {
            Percent = Math.Round(fraction * 100);
            EtaText = remaining is { } r ? EtaPhrase(r) : _s["Transcribe_Eta_Unknown"];
            long now = _clock.GetTimestamp();
            // At most every 10 % or every 10 s, whichever comes first (design/brands/brasscribe/system.md §5).
            bool step = Percent >= _lastAnnouncedPercent + 10;
            if (fraction > 0 && (_lastAnnounce == 0 || step || _clock.GetElapsedTime(_lastAnnounce) >= AnnounceEvery))
            {
                _lastAnnounce = now;
                _lastAnnouncedPercent = Percent;
                _announcer.Announce(_s.Format("Transcribe_ProgressAnnouncement", Percent, StageText, EtaText), AnnouncementKind.Progress);
            }
        });
    }

    public string EtaPhrase(TimeSpan r) =>
        r.TotalSeconds < 60 ? _s["Transcribe_Eta_UnderMinute"]
        : r.TotalMinutes < 90 ? _s.Format("Transcribe_Eta_Minutes", (int)Math.Ceiling(r.TotalMinutes))
        : _s.Format("Transcribe_Eta_Hours", Math.Round(r.TotalHours, 1));

    /// <summary>Engine stage names in plain language.</summary>
    public string StageName(string stage)
    {
        string key = stage.Split('.')[0] switch
        {
            "separate" or "stems" or "layers" or "separation" => "Transcribe_Stage_Separate",
            "beats" or "beat" => "Transcribe_Stage_Beats",
            "transcribe" or "contour" or "f0" or "solo" or "vote" => "Transcribe_Stage_Notes",
            "arrange" => "Transcribe_Stage_Arrange",
            "export" or "render" or "musicxml" => "Transcribe_Stage_Engrave",
            _ => "Transcribe_Stage_Working",
        };
        return _s[key];
    }
}
