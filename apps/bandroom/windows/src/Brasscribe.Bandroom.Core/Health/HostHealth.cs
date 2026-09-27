namespace Brasscribe.Bandroom.Core.Health;

/// <summary>Readings from the host (never from the engine): CPU busy share, memory and free space.</summary>
public interface IHostMetrics
{
    /// <summary>Share of CPU time busy since the previous call, 0..100.</summary>
    double SampleCpuPercent();
    /// <summary>Physical memory: total and available bytes.</summary>
    (ulong Total, ulong Available) Memory();
    /// <summary>Free bytes on the drive holding <paramref name="path"/>.</summary>
    long FreeBytes(string path);
}

/// <summary>Three steps for the neutral 3-segment meter and the word beside it.</summary>
public enum Level { Low = 1, Mid = 2, High = 3 }

public static class HealthWords
{
    /// <summary>Work load: under 40 % Calm, 40–85 % Busy, over 85 % Very busy.</summary>
    public static Level Load(double percent) => percent < 40 ? Level.Low : percent <= 85 ? Level.Mid : Level.High;

    /// <summary>Memory: over 25 % free Plenty free, 10–25 % Getting full, under 10 % Almost full.</summary>
    public static Level Memory(double freeFraction) => freeFraction > 0.25 ? Level.Low : freeFraction >= 0.10 ? Level.Mid : Level.High;

    public static string LoadKey(Level l) => l switch { Level.Low => "Health_Load_Calm", Level.Mid => "Health_Load_Busy", _ => "Health_Load_VeryBusy" };
    public static string MemoryKey(Level l) => l switch { Level.Low => "Health_Memory_Plenty", Level.Mid => "Health_Memory_GettingFull", _ => "Health_Memory_AlmostFull" };

    /// <summary>Whole gigabytes (decimal, as phones show them).</summary>
    public static long Gigabytes(long bytes) => bytes / 1_000_000_000;

    public const long WarnFreeBytes = 10_000_000_000;
    public const long MinFreeBytes = 3_000_000_000;
}

/// <summary>The 30-second average of CPU samples (spec §7: "the higher of CPU and GPU, 30 s average").</summary>
public sealed class LoadAverager(TimeProvider? time = null, TimeSpan? window = null)
{
    private readonly TimeProvider _time = time ?? TimeProvider.System;
    private readonly TimeSpan _window = window ?? TimeSpan.FromSeconds(30);
    private readonly Queue<(DateTimeOffset At, double Value)> _samples = new();

    public double Add(double percent)
    {
        var now = _time.GetUtcNow();
        _samples.Enqueue((now, Math.Clamp(percent, 0, 100)));
        while (_samples.Count > 1 && now - _samples.Peek().At > _window) _samples.Dequeue();
        return Average;
    }

    public double Average => _samples.Count == 0 ? 0 : _samples.Average(s => s.Value);
}

/// <summary>One reading of "This computer", ready for words.</summary>
public sealed record HealthSnapshot(double LoadPercent, double MemoryFreeFraction, long FreeBytes, bool ModelsReady)
{
    public Level Load => HealthWords.Load(LoadPercent);
    public Level Memory => HealthWords.Memory(MemoryFreeFraction);
    public bool LowDisk => FreeBytes < HealthWords.WarnFreeBytes;
}
