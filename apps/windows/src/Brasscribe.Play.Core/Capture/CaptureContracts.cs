namespace Brasscribe.Play.Core.Capture;

public enum CaptureKind
{
    /// <summary>A microphone or line input.</summary>
    Microphone,
    /// <summary>Everything the default output device plays (WASAPI loopback).</summary>
    SystemAudio,
    /// <summary>One app and its child processes (process loopback, Windows build 20348 and later).</summary>
    App,
}

public sealed record CaptureRequest(CaptureKind Kind, string OutputPath, int? ProcessId = null, string? DeviceId = null);

public sealed record AudioApp(int ProcessId, string Name, bool IsPlaying);

public sealed record AudioDevice(string Id, string Name, bool IsDefault);

/// <summary>One buffer's worth of level information, as capture delivers it.</summary>
public readonly record struct CaptureLevel(TimeSpan Elapsed, float Peak, bool SilentFlag);

public sealed record CaptureResult(string Path, TimeSpan Duration, int SampleRate, int Channels, CaptureNotice? Notice);

/// <summary>Records audio to a WAV file. Implemented with WASAPI on Windows.</summary>
public interface ICaptureService
{
    /// <summary>Whether per-app capture is available (Windows build 20348 or later).</summary>
    bool SupportsAppCapture { get; }
    Task<IReadOnlyList<AudioDevice>> ListMicrophonesAsync(CancellationToken ct = default);
    Task<IReadOnlyList<AudioApp>> ListAudioAppsAsync(CancellationToken ct = default);
    Task StartAsync(CaptureRequest request, CancellationToken ct = default);
    Task<CaptureResult> StopAsync(CancellationToken ct = default);
    bool IsCapturing { get; }
    event EventHandler<CaptureLevel>? Level;
    event EventHandler<CaptureNotice>? Notice;
}

/// <summary>Decodes an audio or video file (Media Foundation on Windows) to 16-bit PCM WAV.</summary>
public interface IMediaDecoder
{
    Task<DecodedMedia> DecodeToWavAsync(string inputPath, string outputPath, int? sampleRate = null, CancellationToken ct = default);
}

public sealed record DecodedMedia(string WavPath, TimeSpan Duration, bool HasVideo, int SampleRate, int Channels);
