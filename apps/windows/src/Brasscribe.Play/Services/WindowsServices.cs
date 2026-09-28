using System.Text.Json;
using Brasscribe.Play.Core.Services;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.Windows.ApplicationModel.Resources;
using Windows.Media.Core;
using Windows.Media.Playback;
using Windows.Storage.Pickers;

namespace Brasscribe.Play.Services;

/// <summary>
/// Speaks through UI Automation notification events (Narrator and NVDA read them). Progress uses
/// MostRecent so a newer update replaces an unspoken older one; errors and completions use ImportantAll.
/// </summary>
public sealed class UiaAnnouncer(Func<FrameworkElement?> host, DispatcherQueue queue) : IAnnouncer
{
    public void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        queue.TryEnqueue(() =>
        {
            if (host() is not { } element) return;
            var peer = FrameworkElementAutomationPeer.FromElement(element) ?? FrameworkElementAutomationPeer.CreatePeerForElement(element);
            var (notification, processing, activity) = kind switch
            {
                AnnouncementKind.Important => (AutomationNotificationKind.Other, AutomationNotificationProcessing.ImportantAll, "Important"),
                AnnouncementKind.Progress => (AutomationNotificationKind.ActionCompleted, AutomationNotificationProcessing.MostRecent, "Progress"),
                _ => (AutomationNotificationKind.ActionCompleted, AutomationNotificationProcessing.MostRecent, "Status"),
            };
            peer?.RaiseNotificationEvent(notification, processing, text, activity);
        });
    }
}

public sealed class DispatcherQueueDispatcher(DispatcherQueue queue) : IUiDispatcher
{
    public void Post(Action action)
    {
        if (queue.HasThreadAccess) action();
        else queue.TryEnqueue(() => action());
    }
}

/// <summary>Localised strings from the app's .resw files (MRT Core; works unpackaged).</summary>
public sealed class ResourceStrings : IStrings
{
    private readonly ResourceLoader _loader = new();

    public string this[string key]
    {
        get
        {
            try
            {
                var value = _loader.GetString(key);
                return string.IsNullOrEmpty(value) ? key : value;
            }
            catch (Exception)
            {
                return key;
            }
        }
    }
}

/// <summary>File pickers bound to the main window (required for unpackaged WinUI apps).</summary>
public sealed class WinFileDialogs(Func<nint> hwnd) : IFileDialogs
{
    public async Task<string?> PickOpenAsync(IEnumerable<string> extensions)
    {
        var picker = new FileOpenPicker { SuggestedStartLocation = PickerLocationId.MusicLibrary, ViewMode = PickerViewMode.List };
        foreach (var e in extensions) picker.FileTypeFilter.Add(e);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd());
        var file = await picker.PickSingleFileAsync();
        return file?.Path;
    }

    public async Task<SaveTarget?> PickSaveAsync(string suggestedName, string extension, string description)
    {
        var picker = new FileSavePicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            SuggestedFileName = Path.GetFileNameWithoutExtension(suggestedName),
        };
        picker.FileTypeChoices.Add(description, [extension]);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd());
        var file = await picker.PickSaveFileAsync();
        if (file is null) return null;
        var stream = new FileStream(file.Path, FileMode.Create, FileAccess.Write, FileShare.None);
        return new SaveTarget(stream, file.Name);
    }

    public async Task<string?> PickFolderAsync()
    {
        var picker = new FolderPicker { SuggestedStartLocation = PickerLocationId.DocumentsLibrary };
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd());
        var folder = await picker.PickSingleFolderAsync();
        return folder?.Path;
    }
}

/// <summary>
/// Prints a PDF through the PDF app the player uses (the shell's "print" verb opens its print dialog).
/// When no app is registered for printing PDFs, the PDF opens instead so it can be printed from there.
/// </summary>
public sealed class ShellPdfPrinter : IPrinter
{
    public bool CanPrint => OperatingSystem.IsWindows();

    public Task PrintAsync(string pdfPath)
    {
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(pdfPath) { Verb = "print", UseShellExecute = true });
        }
        catch (System.ComponentModel.Win32Exception)
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(pdfPath) { UseShellExecute = true });
        }
        return Task.CompletedTask;
    }
}

/// <summary>Settings in %LOCALAPPDATA%\Brasscribe\Play\settings.json (the app runs unpackaged).</summary>
public sealed class JsonSettingsStore : ISettingsStore
{
    private readonly string _path;
    private readonly Dictionary<string, JsonElement> _values;

    public JsonSettingsStore()
    {
        var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Brasscribe", "Play");
        Directory.CreateDirectory(dir);
        _path = Path.Combine(dir, "settings.json");
        try { _values = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(File.ReadAllText(_path)) ?? []; }
        catch (Exception e) when (e is IOException or JsonException) { _values = []; }
    }

    public static string WorkDirectory =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Brasscribe", "Play", "work");

    public T Get<T>(string key, T fallback)
    {
        if (!_values.TryGetValue(key, out var v)) return fallback;
        try { return v.Deserialize<T>() ?? fallback; }
        catch (JsonException) { return fallback; }
    }

    public void Set<T>(string key, T value)
    {
        _values[key] = JsonSerializer.SerializeToElement(value);
        try { File.WriteAllText(_path, JsonSerializer.Serialize(_values)); }
        catch (IOException) { }
    }
}

/// <summary>
/// The original recording or video through Windows' media player (for "listen to this bar"), at the
/// level-matching volume, fading out over the band's 80 ms when it stops.
/// </summary>
public sealed class MediaPlayerOriginal : IOriginalPlayer, IDisposable
{
    private readonly MediaPlayer _player = new() { AutoPlay = false };
    private readonly DispatcherQueue? _queue;
    private TimeSpan? _loopStart, _loopEnd, _stopAt;
    private double _volume = 1;
    private int _fade;

    public MediaPlayerOriginal(DispatcherQueue? queue = null)
    {
        _queue = queue;
        _player.PlaybackSession.PositionChanged += (s, _) =>
        {
            if (_loopEnd is { } end && s.Position >= end && _loopStart is { } start) s.Position = start;
            else if (_stopAt is { } stop && s.Position >= stop) EndRange();
        };
        _player.MediaEnded += (_, _) => EndRange();
    }

    /// <summary>A range played once reached its end ("Listen to this bar" goes back to Listen).</summary>
    public event EventHandler? RangeEnded;

    private void EndRange()
    {
        if (_stopAt is null) return;
        _stopAt = null;
        FadeThenPause();
        if (_queue is null) RangeEnded?.Invoke(this, EventArgs.Empty);
        else _queue.TryEnqueue(() => RangeEnded?.Invoke(this, EventArgs.Empty));
    }

    public MediaPlayer Player => _player;
    public bool HasMedia { get; private set; }
    public bool HasVideo { get; private set; }

    public void Open(string path, bool hasVideo)
    {
        _player.Source = MediaSource.CreateFromUri(new Uri(path));
        HasMedia = true;
        HasVideo = hasVideo;
    }

    public void Play()
    {
        CancelFade();
        _player.Play();
    }

    public void Pause()
    {
        _loopStart = _loopEnd = _stopAt = null;
        FadeThenPause();
    }

    /// <summary>The level-matching volume (Core's RecordingLevel); the media player cannot go above 1.</summary>
    public double Volume
    {
        get => _volume;
        set
        {
            _volume = Math.Clamp(value, 0, 1);
            _player.Volume = _volume;
        }
    }

    /// <summary>Ramps the volume down over the band's stop fade (80 ms), then pauses, so stopping never clicks.</summary>
    private async void FadeThenPause()
    {
        int fade = ++_fade;
        const int steps = 8;
        for (int i = 1; i <= steps; i++)
        {
            await Task.Delay(TimeSpan.FromMilliseconds(Brasscribe.Play.Core.Playback.BufferedSynthOutput.StopFadeMs / steps));
            if (fade != _fade) return; // played again meanwhile
            _player.Volume = _volume * (1 - (double)i / steps);
        }
        _player.Pause();
        _player.Volume = _volume;
    }

    private void CancelFade()
    {
        _fade++;
        _player.Volume = _volume;
    }

    public bool IsPlaying => _player.PlaybackSession.PlaybackState == MediaPlaybackState.Playing;

    public bool IsMuted
    {
        get => _player.IsMuted;
        set => _player.IsMuted = value;
    }

    public double Rate
    {
        get => _player.PlaybackSession.PlaybackRate;
        set => _player.PlaybackSession.PlaybackRate = value;
    }

    public void PlayRange(TimeSpan start, TimeSpan end, bool loop)
    {
        _loopStart = loop ? start : null;
        _loopEnd = loop ? end : null;
        _stopAt = loop ? null : end;
        CancelFade();
        _player.PlaybackSession.Position = start;
        _player.Play();
    }

    public void Stop()
    {
        _loopStart = _loopEnd = _stopAt = null;
        FadeThenPause();
    }

    public TimeSpan Position
    {
        get => _player.PlaybackSession.Position;
        set => _player.PlaybackSession.Position = value;
    }

    public void Dispose() => _player.Dispose();
}
