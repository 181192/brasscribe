namespace Brasscribe.Play.Core.Engine;

/// <summary>A progress snapshot in plain terms for the UI.</summary>
public sealed record TranscriptionProgress(
    double Fraction,
    TimeSpan Elapsed,
    TimeSpan? Remaining,
    string? CurrentStage,
    int StagesDone,
    int StagesTotal);

/// <summary>
/// Estimates the time left from the share of stages done. The engine sends no ETA, so this is an
/// estimate: remaining = elapsed × (1 − f) / f, smoothed so the number does not jump around, and
/// withheld until enough of the job has run to say anything useful.
/// </summary>
public sealed class ProgressEstimator(TimeProvider? clock = null)
{
    private const double MinFraction = 0.05;
    private const double Smoothing = 0.3;

    private readonly TimeProvider _clock = clock ?? TimeProvider.System;
    private long? _startTicks;
    private double? _smoothedRemainingSeconds;

    public double Fraction { get; private set; }

    public void Start() => _startTicks = _clock.GetTimestamp();

    public TimeSpan Elapsed => _startTicks is { } s ? _clock.GetElapsedTime(s) : TimeSpan.Zero;

    public TimeSpan? Update(double fraction)
    {
        _startTicks ??= _clock.GetTimestamp();
        Fraction = Math.Clamp(fraction, 0, 1);
        if (Fraction >= 1) return _smoothedRemainingSeconds is null ? null : TimeSpan.Zero;
        if (Fraction < MinFraction) return null;

        double elapsed = Elapsed.TotalSeconds;
        double raw = elapsed * (1 - Fraction) / Fraction;
        _smoothedRemainingSeconds = _smoothedRemainingSeconds is { } prev
            ? prev + Smoothing * (raw - prev)
            : raw;
        return TimeSpan.FromSeconds(Math.Max(0, _smoothedRemainingSeconds.Value));
    }

    public TimeSpan? Remaining =>
        _smoothedRemainingSeconds is { } s ? TimeSpan.FromSeconds(Math.Max(0, s)) : null;
}
