namespace Brasscribe.Play.Core.Capture;

public enum CaptureNoticeKind
{
    /// <summary>Nothing but digital silence arrived while something should be playing.</summary>
    SilenceWhilePlaying,
    /// <summary>The chosen app plays nothing at all.</summary>
    NothingPlaying,
    /// <summary>The input level is clipping.</summary>
    TooLoud,
}

/// <summary>A message the capture screen shows (and announces) instead of silently recording silence.</summary>
public sealed record CaptureNotice(CaptureNoticeKind Kind, TimeSpan At);

/// <summary>
/// Watches capture levels for the cases where the recording would be useless. Protected (DRM)
/// playback is blocked by Windows' trusted audio path: loopback then delivers silent buffers even
/// though the app is playing. The same pattern also appears when nothing plays, so the notice
/// names both causes and the app says so rather than guessing.
/// </summary>
public sealed class SilenceWatch(TimeSpan? after = null, float silencePeak = 1e-4f, float clipPeak = 0.999f)
{
    private readonly TimeSpan _after = after ?? TimeSpan.FromSeconds(4);
    private TimeSpan? _silentSince;
    private int _clipRun;
    private bool _silenceReported, _clipReported;

    /// <summary>Set by the caller when the audio session of the captured app reports it is playing.</summary>
    public bool SourceReportsPlaying { get; set; }

    public TimeSpan Elapsed { get; private set; }

    /// <summary>Feeds one buffer's level; returns a notice the first time a condition holds.</summary>
    public CaptureNotice? Feed(CaptureLevel level)
    {
        Elapsed = level.Elapsed;
        bool silent = level.SilentFlag || level.Peak < silencePeak;
        if (silent)
        {
            _silentSince ??= level.Elapsed;
            if (!_silenceReported && level.Elapsed - _silentSince.Value >= _after)
            {
                _silenceReported = true;
                return new CaptureNotice(SourceReportsPlaying ? CaptureNoticeKind.SilenceWhilePlaying : CaptureNoticeKind.NothingPlaying,
                    level.Elapsed);
            }
        }
        else
        {
            _silentSince = null;
            _silenceReported = false;
        }

        _clipRun = level.Peak >= clipPeak ? _clipRun + 1 : 0;
        if (_clipRun >= 8 && !_clipReported)
        {
            _clipReported = true;
            return new CaptureNotice(CaptureNoticeKind.TooLoud, level.Elapsed);
        }
        return null;
    }

    public void Reset()
    {
        _silentSince = null;
        _silenceReported = _clipReported = false;
        _clipRun = 0;
    }

    /// <summary>Level in dBFS for a peak value, floored at -90.</summary>
    public static double Dbfs(float peak) => peak <= 0 ? -90 : Math.Max(-90, 20 * Math.Log10(peak));

    /// <summary>Plain-language band for the input meter ("Input level, good").</summary>
    public static InputBand Band(float peak) => Dbfs(peak) switch
    {
        < -50 => InputBand.Silent,
        < -30 => InputBand.Low,
        < -3 => InputBand.Good,
        _ => InputBand.TooLoud,
    };
}

public enum InputBand { Silent, Low, Good, TooLoud }
