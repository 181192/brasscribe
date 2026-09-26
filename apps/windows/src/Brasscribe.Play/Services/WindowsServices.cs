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

/// <summary>The original recording or video through Windows' media player (for "listen to this bar").</summary>
public sealed class MediaPlayerOriginal : IOriginalPlayer, IDisposable
{
    private readonly MediaPlayer _player = new() { AutoPlay = false };
    private TimeSpan? _loopStart, _loopEnd;

    public MediaPlayerOriginal()
    {
        _player.PlaybackSession.PositionChanged += (s, _) =>
        {
            if (_loopEnd is { } end && s.Position >= end && _loopStart is { } start) s.Position = start;
        };
    }

    public MediaPlayer Player => _player;
    public bool HasMedia { get; private set; }

    public void Open(string path)
    {
        _player.Source = MediaSource.CreateFromUri(new Uri(path));
        HasMedia = true;
    }

    public void PlayRange(TimeSpan start, TimeSpan end, bool loop)
    {
        _loopStart = loop ? start : null;
        _loopEnd = loop ? end : null;
        _player.PlaybackSession.Position = start;
        _player.Play();
    }

    public void Stop()
    {
        _loopStart = _loopEnd = null;
        _player.Pause();
    }

    public TimeSpan Position
    {
        get => _player.PlaybackSession.Position;
        set => _player.PlaybackSession.Position = value;
    }

    public void Dispose() => _player.Dispose();
}
