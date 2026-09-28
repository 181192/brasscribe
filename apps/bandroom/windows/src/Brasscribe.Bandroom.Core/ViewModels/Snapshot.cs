using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.State;

namespace Brasscribe.Bandroom.Core.ViewModels;

/// <summary>The job being made now, in the flyout's words.</summary>
public sealed record JobView(string? Title, string StepKey, double Fraction, int? MinutesLeft, string? Device = null)
{
    /// <summary>The Play step an engine stage belongs to (Play's step names, §7).</summary>
    public static string StepKeyOf(string? stage) => (stage ?? "").Split('.')[0] switch
    {
        "separate" or "stems" or "separation" => "Step_Separate",
        "layers" => "Step_Layers",
        "beats" or "beat" => "Step_Beat",
        "transcribe" or "contour" or "f0" or "solo" or "vote" => "Step_Notes",
        "arrange" => "Step_Arrange",
        "export" or "render" or "musicxml" or "engrave" => "Step_Layout",
        _ => "Step_Prepare",
    };

    /// <summary>The running job, if any: its current stage, progress and a time-left estimate.</summary>
    public static JobView? From(IReadOnlyList<JobInfo> jobs, DateTimeOffset now)
    {
        var job = jobs.Where(j => j.Status == "running").OrderBy(j => j.Started ?? j.Created).FirstOrDefault();
        if (job is null) return null;
        var stage = job.Stages?.FirstOrDefault(s => s.Status == "started")?.Name;
        int? minutes = null;
        if (job.Started is { } started && job.Progress is > 0.02 and < 1)
        {
            double elapsed = now.ToUnixTimeMilliseconds() / 1000.0 - started;
            double left = elapsed / job.Progress * (1 - job.Progress);
            if (elapsed > 0) minutes = Math.Max(1, (int)Math.Ceiling(left / 60));
        }
        return new JobView(job.Title, StepKeyOf(stage), job.Progress, minutes, job.DeviceName);
    }
}

/// <summary>For the tech disclosure: addresses, port, version, device, server id, data folder.</summary>
/// <summary>The tech-person details; <see cref="Build"/> is the running engine's, <see cref="Workspace"/> the app's own stamp.</summary>
public sealed record TechDetails(IReadOnlyList<string> Addresses, int? Port, string Version, string RunsOn, string? ServerId, string DataDir,
    string? Build = null, string? Workspace = null);

/// <summary>
/// Everything the flyout shows at one moment. DownloadProgress is "3.1 of 9.8 GB · about 12 min left" while the
/// models download (or are paused), else null.
/// </summary>
public sealed record BandroomSnapshot(
    StateInputs Inputs,
    string Header,
    StatusInfo? Status,
    JobView? Job,
    HealthSnapshot? Health,
    string SpeedKey,
    TechDetails Tech,
    string? DownloadProgress = null);
