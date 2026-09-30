using System.Collections.ObjectModel;
using Brasscribe.Play.Core.Capture;
using Brasscribe.Play.Core.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>An audio source ready for "What is this?": a decoded WAV plus what it came from.</summary>
public sealed record SourceAudio(string WavPath, string DisplayName, TimeSpan Duration, string? OriginalPath, bool HasVideo);

/// <summary>
/// Start screen: import a file (audio, video or MusicXML), record the microphone, the whole system
/// output or one app. Recording watches for silence so protected (DRM) playback is reported
/// instead of recorded as nothing.
/// </summary>
public sealed partial class StartViewModel : ObservableObject
{
    private readonly ICaptureService _capture;
    private readonly IMediaDecoder _decoder;
    private readonly IFileDialogs _dialogs;
    private readonly IAnnouncer _announcer;
    private readonly IStrings _s;
    private readonly IUiDispatcher _ui;
    private readonly string _workDir;
    private SilenceWatch _watch = new();
    /// <summary>The take (decoded import or recording) the app is working with now; the one before it is deleted.</summary>
    private string? _take;

    public StartViewModel(ICaptureService capture, IMediaDecoder decoder, IFileDialogs dialogs, IAnnouncer announcer,
        IStrings strings, IUiDispatcher ui, string workDir)
    {
        _ui = ui;
        _capture = capture;
        _decoder = decoder;
        _dialogs = dialogs;
        _announcer = announcer;
        _s = strings;
        // Takes live in their own folder, emptied at start: nothing refers to a take once the app has closed
        // (the engine keeps its own copy, and "Your scores" keeps the score, not the recording).
        _workDir = Path.Combine(workDir, "takes");
        Directory.CreateDirectory(_workDir);
        Prune(_workDir);
        _capture.Level += (_, level) => _ui.Post(() => OnLevel(level));
        _capture.Notice += (_, n) => _ui.Post(() => ShowNotice(n));
    }

    /// <summary>Raised when an audio source is ready for the "What is this?" step.</summary>
    public event EventHandler<SourceAudio>? SourceReady;

    /// <summary>Raised when a MusicXML file was opened: it goes straight to the score.</summary>
    public event EventHandler<string>? ScoreOpened;

    public bool SupportsAppCapture => _capture.SupportsAppCapture;

    public ObservableCollection<AudioApp> Apps { get; } = [];

    [ObservableProperty] public partial AudioApp? SelectedApp { get; set; }

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(RecordMicrophoneCommand), nameof(RecordSystemAudioCommand), nameof(RecordAppCommand), nameof(StopRecordingCommand), nameof(ImportCommand))]
    public partial bool IsRecording { get; set; }

    [ObservableProperty] public partial bool IsBusy { get; set; }

    /// <summary>0..1 for the level meter.</summary>
    [ObservableProperty] public partial double InputLevel { get; set; }

    /// <summary>"Input level, good" and so on; the meter's accessible value.</summary>
    [ObservableProperty] public partial string InputLevelText { get; set; } = "";

    [ObservableProperty] public partial string? NoticeText { get; set; }
    [ObservableProperty] public partial string? ErrorText { get; set; }
    [ObservableProperty] public partial string RecordingTime { get; set; } = "0:00";

    [RelayCommand(CanExecute = nameof(CanStart))]
    private async Task ImportAsync()
    {
        ErrorText = null;
        var path = await _dialogs.PickOpenAsync(MediaTypes.All);
        if (path is null) return;
        await OpenPathAsync(path);
    }

    /// <summary>Also used for drag-and-drop, "Open with" and the command line.</summary>
    public async Task OpenPathAsync(string path)
    {
        ErrorText = null;
        if (MediaTypes.IsLink(path))
        {
            Fail(_s["Start_Error_Link"]);
            return;
        }
        switch (MediaTypes.Classify(path))
        {
            case MediaKind.Score:
                ScoreOpened?.Invoke(this, path);
                return;
            case MediaKind.Unsupported:
                Fail(_s.Format("Start_Error_Unsupported", Path.GetFileName(path)));
                return;
        }
        IsBusy = true;
        string wav = Path.Combine(_workDir, Path.GetFileNameWithoutExtension(path) + "-" + Guid.NewGuid().ToString("N")[..8] + ".wav");
        try
        {
            var media = await _decoder.DecodeToWavAsync(path, wav);
            var source = new SourceAudio(media.WavPath, Path.GetFileName(path), media.Duration, path, media.HasVideo);
            UseTake(media.WavPath);
            _announcer.Announce(_s.Format("Start_Imported", source.DisplayName, DurationText(media.Duration)), AnnouncementKind.Important);
            SourceReady?.Invoke(this, source);
        }
        catch (Exception e) when (e is IOException or InvalidDataException or NotSupportedException or UnauthorizedAccessException or System.Runtime.InteropServices.COMException)
        {
            Delete(wav); // what was written before the decoder stopped
            Fail(_s.Format(MediaTypes.NeedsCodec(path) ? "Start_Error_NeedsCodec" : "Start_Error_Decode", Path.GetFileName(path)));
        }
        finally
        {
            IsBusy = false;
        }
    }

    [RelayCommand(CanExecute = nameof(CanStart))]
    private Task RecordMicrophoneAsync() => StartCapture(CaptureKind.Microphone, null);

    [RelayCommand(CanExecute = nameof(CanStart))]
    private Task RecordSystemAudioAsync() => StartCapture(CaptureKind.SystemAudio, null);

    [RelayCommand(CanExecute = nameof(CanStart))]
    private Task RecordAppAsync()
    {
        if (!SupportsAppCapture)
        {
            Fail(_s["Start_Error_AppCaptureUnsupported"]);
            return Task.CompletedTask;
        }
        if (SelectedApp is null)
        {
            Fail(_s["Start_Error_ChooseApp"]);
            return Task.CompletedTask;
        }
        return StartCapture(CaptureKind.App, SelectedApp.ProcessId);
    }

    [RelayCommand]
    private async Task RefreshAppsAsync()
    {
        Apps.Clear();
        foreach (var a in await _capture.ListAudioAppsAsync()) Apps.Add(a);
    }

    [RelayCommand(CanExecute = nameof(IsRecording))]
    private async Task StopRecordingAsync()
    {
        var result = await _capture.StopAsync();
        IsRecording = false;
        InputLevel = 0;
        _announcer.Announce(_s.Format("Start_RecordingStopped", DurationText(result.Duration)), AnnouncementKind.Important);
        if (result.Duration < TimeSpan.FromSeconds(1))
        {
            Delete(result.Path);
            Fail(_s["Start_Error_TooShort"]);
            return;
        }
        UseTake(result.Path);
        SourceReady?.Invoke(this, new SourceAudio(result.Path, ScoreTitles.Recording(DateTimeOffset.Now, _s), result.Duration, null, false));
    }

    /// <summary>A new take replaces the last one, whose WAV and level-matched copies are deleted.</summary>
    private void UseTake(string path)
    {
        if (_take is { } old && !string.Equals(old, path, StringComparison.OrdinalIgnoreCase))
        {
            Delete(old);
            string stem = Path.GetFileNameWithoutExtension(old);
            try
            {
                foreach (var copy in Directory.EnumerateFiles(_workDir, stem + ".boost*")) Delete(copy);
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
        }
        _take = path;
    }

    /// <summary>Takes left by an earlier run of the app.</summary>
    private static void Prune(string dir)
    {
        try
        {
            foreach (var file in Directory.EnumerateFiles(dir)) Delete(file);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    /// <summary>Best effort: a file still open elsewhere (the media player) goes the next time the app starts.</summary>
    private static void Delete(string path)
    {
        try { File.Delete(path); }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }

    private bool CanStart() => !IsRecording;

    private async Task StartCapture(CaptureKind kind, int? pid)
    {
        ErrorText = NoticeText = null;
        _watch = new SilenceWatch { SourceReportsPlaying = kind == CaptureKind.App && SelectedApp?.IsPlaying == true };
        string path = Path.Combine(_workDir, $"recording-{DateTime.Now:yyyyMMdd-HHmmss}.wav");
        try
        {
            await _capture.StartAsync(new CaptureRequest(kind, path, pid));
        }
        catch (UnauthorizedAccessException)
        {
            Fail(_s["Start_Error_MicrophonePermission"]);
            return;
        }
        catch (Exception e) when (e is InvalidOperationException or System.Runtime.InteropServices.COMException)
        {
            Fail(_s.Format("Start_Error_Capture", e.Message));
            return;
        }
        IsRecording = true;
        _announcer.Announce(_s["Start_RecordingStarted"], AnnouncementKind.Important);
    }

    private void OnLevel(CaptureLevel level)
    {
        InputLevel = Math.Clamp((SilenceWatch.Dbfs(level.Peak) + 60) / 60, 0, 1);
        InputLevelText = _s[$"Start_Level_{SilenceWatch.Band(level.Peak)}"];
        RecordingTime = DurationShort(level.Elapsed);
        if (_watch.Feed(level) is { } notice) ShowNotice(notice);
    }

    private void ShowNotice(CaptureNotice notice)
    {
        NoticeText = _s[$"Start_Notice_{notice.Kind}"];
        _announcer.Announce(NoticeText, AnnouncementKind.Important);
    }

    private void Fail(string message)
    {
        ErrorText = message;
        _announcer.Announce(message, AnnouncementKind.Important);
    }

    public string DurationText(TimeSpan d) =>
        d.TotalMinutes >= 1
            ? _s.Format("Duration_MinutesSeconds", (int)d.TotalMinutes, d.Seconds)
            : _s.Format("Duration_Seconds", (int)Math.Round(d.TotalSeconds));

    private static string DurationShort(TimeSpan d) => $"{(int)d.TotalMinutes}:{d.Seconds:00}";
}
