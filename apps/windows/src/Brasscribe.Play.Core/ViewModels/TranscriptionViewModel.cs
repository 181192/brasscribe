using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Scores;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

public sealed record TranscriptionResult(string JobId, Composition Composition, string MusicXml, IReadOnlyList<string> Outputs, SourceAudio Source);

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
    [ObservableProperty] public partial string Title { get; set; } = "";
    [ObservableProperty] public partial string? DeviceText { get; set; }

    public async Task RunAsync(SourceAudio source, SourceKindOption kind)
    {
        _cts?.Cancel();
        _cts = new CancellationTokenSource();
        var ct = _cts.Token;
        var engine = _engine();
        var estimator = new ProgressEstimator(_clock);
        IsRunning = true;
        ErrorText = null;
        Percent = 0;
        Title = source.DisplayName;
        StageText = _s["Transcribe_Stage_Upload"];
        EtaText = _s["Transcribe_Eta_Unknown"];
        _announcer.Announce(_s.Format("Transcribe_Started", source.DisplayName, kind.Label), AnnouncementKind.Important);
        try
        {
            var health = await engine.GetHealthAsync(ct);
            DeviceText = _s.Format("Transcribe_Device", health.Device.ToUpperInvariant());

            AudioRef audio;
            await using (var file = File.OpenRead(source.WavPath))
                audio = await engine.UploadAudioAsync(file, Path.GetFileName(source.WavPath), ct);

            var job = await engine.CreateJobAsync(new JobCreate(audio.AudioId, kind.Profile, RenderAudio: true,
                Title: Path.GetFileNameWithoutExtension(source.DisplayName)), ct);
            _jobId = job.Id;
            estimator.Start();

            await foreach (var ev in engine.StreamEventsAsync(job.Id, ct: ct))
            {
                if (ev.Type == "stage")
                {
                    if (ev.Fraction is { } f) Update(estimator, f);
                    if (ev.Stage is { } stage && ev.Status == "started") StageText = StageName(stage);
                    if (ev.Device is { } device) DeviceText = _s.Format("Transcribe_Device", device.ToUpperInvariant());
                }
                else if (ev.Type == "job" && ev.Status is { } status)
                {
                    if (status == JobStatus.Failed) throw new EngineException(ev.Error ?? _s["Transcribe_Failed"]);
                    if (status == JobStatus.Cancelled) throw new OperationCanceledException();
                }
            }

            job = await engine.GetJobAsync(job.Id, ct);
            if (job.Status != JobStatus.Succeeded) throw new EngineException(job.Error ?? _s["Transcribe_Failed"]);
            var composition = await engine.GetCompositionAsync(job.Id, ct);
            string xml;
            await using (var s = await engine.DownloadAsync(job.Id, JobDownload.MusicXml, ct))
            using (var reader = new StreamReader(s))
                xml = await reader.ReadToEndAsync(ct);

            Percent = 100;
            StageText = _s["Transcribe_Done"];
            EtaText = "";
            _announcer.Announce(_s["Transcribe_Done"], AnnouncementKind.Important);
            Completed?.Invoke(this, new TranscriptionResult(job.Id, composition, xml, job.Outputs ?? [], source));
        }
        catch (OperationCanceledException)
        {
            StageText = _s["Transcribe_Cancelled"];
            _announcer.Announce(StageText, AnnouncementKind.Important);
        }
        catch (EngineException e)
        {
            ErrorText = e.Message;
            _announcer.Announce(_s.Format("Transcribe_Error", e.Message), AnnouncementKind.Important);
        }
        finally
        {
            IsRunning = false;
            _jobId = null;
        }
    }

    [RelayCommand(CanExecute = nameof(IsRunning))]
    private async Task CancelAsync()
    {
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
            if (_lastAnnounce == 0 || _clock.GetElapsedTime(_lastAnnounce) >= AnnounceEvery)
            {
                _lastAnnounce = now;
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
