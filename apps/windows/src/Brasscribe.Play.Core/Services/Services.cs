using System.Xml.Linq;

namespace Brasscribe.Play.Core.Services;

public enum AnnouncementKind
{
    /// <summary>A polite status message; a newer one replaces a queued older one.</summary>
    Status,
    /// <summary>Progress updates; throttled and only the most recent is spoken.</summary>
    Progress,
    /// <summary>Errors and completions that must be heard.</summary>
    Important,
}

/// <summary>Speaks through the screen reader (UIA notification events on Windows). Never self-voices.</summary>
public interface IAnnouncer
{
    void Announce(string text, AnnouncementKind kind = AnnouncementKind.Status);
}

public interface IUiDispatcher
{
    void Post(Action action);
}

public sealed record SaveTarget(Stream Stream, string DisplayName);

public interface IFileDialogs
{
    Task<string?> PickOpenAsync(IEnumerable<string> extensions);
    Task<SaveTarget?> PickSaveAsync(string suggestedName, string extension, string description);
}

/// <summary>Localised strings by resource key (.resw on Windows).</summary>
public interface IStrings
{
    string this[string key] { get; }
    string Format(string key, params object[] args) =>
        string.Format(System.Globalization.CultureInfo.CurrentCulture, this[key], args);
}

/// <summary>Starts the audio device that drains the synth buffer (WASAPI shared mode on Windows).</summary>
public interface IAudioOutput : IDisposable
{
    void Start(Playback.BufferedSynthOutput source);
    void Stop();
}

/// <summary>Plays the original recording (for "listen to this bar" and original-vs-score).</summary>
public interface IOriginalPlayer
{
    bool HasMedia { get; }
    /// <summary>The original has a picture (video file), shown in the score screen and picture-in-picture.</summary>
    bool HasVideo { get; }
    void Open(string path, bool hasVideo);
    void PlayRange(TimeSpan start, TimeSpan end, bool loop);
    void Play();
    void Pause();
    void Stop();
    bool IsPlaying { get; }
    bool IsMuted { get; set; }
    /// <summary>Playback rate, 1 = normal.</summary>
    double Rate { get; set; }
    TimeSpan Position { get; set; }
}

public interface ISettingsStore
{
    T Get<T>(string key, T fallback);
    void Set<T>(string key, T value);
}

/// <summary>Strings from a .resw file (the same files the WinUI app ships); used off Windows and in tests.</summary>
public sealed class ReswStrings : IStrings
{
    private readonly Dictionary<string, string> _values;

    public ReswStrings(Dictionary<string, string> values) => _values = values;

    public static ReswStrings Load(string path) => new(Parse(XDocument.Load(path)));

    public static Dictionary<string, string> Parse(XDocument doc) =>
        doc.Root!.Elements("data").ToDictionary(
            d => (string)d.Attribute("name")!,
            d => (string?)d.Element("value") ?? "");

    public IReadOnlyDictionary<string, string> Values => _values;

    /// <summary>x:Uid keys are "Name.Property"; code keys are plain. Missing keys return the key, so gaps are visible.</summary>
    public string this[string key] => _values.TryGetValue(key, out var v) ? v : key;
}

public sealed class InMemorySettings : ISettingsStore
{
    private readonly Dictionary<string, object?> _values = [];
    public T Get<T>(string key, T fallback) => _values.TryGetValue(key, out var v) && v is T t ? t : fallback;
    public void Set<T>(string key, T value) => _values[key] = value;
}
