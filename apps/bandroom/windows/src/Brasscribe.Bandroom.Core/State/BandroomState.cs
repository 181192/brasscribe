using Brasscribe.Bandroom.Core.Downloads;
using Brasscribe.Bandroom.Core.Supervisor;

namespace Brasscribe.Bandroom.Core.State;

/// <summary>What the icon, tooltip and status line say (design/server-app.md §6.1).</summary>
public enum DisplayState { SettingUp, Starting, Running, Busy, NeedsAttention, Stopped, Updating, Error }

/// <summary>The badge drawn on the mark: a shape per state, never colour alone.</summary>
public enum TrayBadge { None, DownArrow, Dots, Pie, Triangle, Square, CircularArrow, CrossCircle }

/// <summary>The one primary button of the flyout.</summary>
public enum PrimaryAction { None, PairPhone, StartEngine, FinishSetup, TryAgain, Fix }

public enum ProblemKind { NoFreePort, LowDisk, MissingDownload, FirewallBlocked, PublicNetwork, KeyRefused, UpdateFailed }

/// <summary>A Needs-attention problem (§6.2): a title, one sentence why, the fix, and details for the tech person.</summary>
public sealed record Problem(ProblemKind Kind, string Title, string Why, string FixLabel, string Details);

/// <summary>Everything that decides the state, gathered from the supervisor, setup, host and engine status.</summary>
public sealed record StateInputs(
    EngineState Engine,
    bool SetupComplete,
    double SetupFraction,
    bool Updating,
    IReadOnlyList<Problem> Problems,
    double? JobFraction,
    int OnlineDevices);

public sealed record DisplayInfo(
    DisplayState State,
    TrayBadge Badge,
    int PieEighths,
    string Tooltip,
    string StatusWord,
    string StatusSub,
    PrimaryAction Primary,
    string PrimaryLabel,
    Problem? Problem);

public static class StateRules
{
    /// <summary>
    /// Precedence when more than one applies: Error › Needs attention › Updating › Setting up › Busy ›
    /// Starting › Running › Stopped. With a problem while busy, the badge is the triangle and the job
    /// block still shows progress.
    /// </summary>
    public static DisplayState Resolve(StateInputs i)
    {
        if (i.Engine == EngineState.Error) return DisplayState.Error;
        if (i.Problems.Count > 0) return DisplayState.NeedsAttention;
        if (i.Updating) return DisplayState.Updating;
        if (!i.SetupComplete && i.Engine is not (EngineState.Running or EngineState.Starting)) return DisplayState.SettingUp;
        if (i.Engine == EngineState.Running && i.JobFraction is not null) return DisplayState.Busy;
        if (i.Engine is EngineState.Starting) return DisplayState.Starting;
        if (i.Engine == EngineState.Running) return DisplayState.Running;
        return DisplayState.Stopped;
    }

    public static TrayBadge Badge(DisplayState s) => s switch
    {
        DisplayState.SettingUp => TrayBadge.DownArrow,
        DisplayState.Starting => TrayBadge.Dots,
        DisplayState.Busy => TrayBadge.Pie,
        DisplayState.NeedsAttention => TrayBadge.Triangle,
        DisplayState.Stopped => TrayBadge.Square,
        DisplayState.Updating => TrayBadge.CircularArrow,
        DisplayState.Error => TrayBadge.CrossCircle,
        _ => TrayBadge.None,
    };

    /// <summary>Progress as a static pie in 8 steps (no animation, 2.3.3).</summary>
    public static int Eighths(double fraction) => (int)Math.Clamp(Math.Floor(fraction * 8), 0, 8);

    public static int Percent(double fraction) => (int)Math.Clamp(Math.Round(fraction * 100), 0, 100);

    public static DisplayInfo Describe(StateInputs i, IStrings s)
    {
        var state = Resolve(i);
        var problem = state == DisplayState.NeedsAttention ? i.Problems[0] : null;
        double fraction = state is DisplayState.SettingUp or DisplayState.Updating ? i.SetupFraction : i.JobFraction ?? 0;
        int pct = Percent(fraction);
        string tooltip = state switch
        {
            DisplayState.SettingUp => s.Format("Tooltip_Setup", pct),
            DisplayState.Starting => s["Tooltip_Starting"],
            DisplayState.Running => i.OnlineDevices == 1 ? s["Tooltip_Running_One"] : s.Format("Tooltip_Running", i.OnlineDevices),
            DisplayState.Busy => s.Format("Tooltip_Busy", pct),
            DisplayState.NeedsAttention => s.Format("Tooltip_Attention", problem!.Title),
            DisplayState.Updating => s["Tooltip_Updating"],
            DisplayState.Error => s["Error_Title"],
            _ => s["Tooltip_Stopped"],
        };
        string word = state switch
        {
            DisplayState.SettingUp => s["Status_Setup"],
            DisplayState.Starting => s["Status_Starting"],
            DisplayState.Running => s["Status_Running"],
            DisplayState.Busy => s["Status_Running"] + " · " + s["Status_MakingScore"],
            DisplayState.NeedsAttention => s["Status_Attention"],
            DisplayState.Updating => s["Status_Updating"],
            DisplayState.Error => s["Status_Error"],
            _ => s["Status_Stopped"],
        };
        string sub = state switch
        {
            DisplayState.Running => s["Status_Running_Idle"],
            DisplayState.Stopped => s["Status_Stopped_Sub"],
            DisplayState.Updating => s.Format("Update_Progress", pct) + " " + s["Status_Updating_Sub"],
            DisplayState.Error => s["Error_Why"],
            DisplayState.NeedsAttention => problem!.Why,
            _ => "",
        };
        var primary = state switch
        {
            DisplayState.SettingUp => PrimaryAction.FinishSetup,
            DisplayState.Running or DisplayState.Busy => PrimaryAction.PairPhone,
            DisplayState.NeedsAttention => PrimaryAction.Fix,
            DisplayState.Stopped => PrimaryAction.StartEngine,
            DisplayState.Error => PrimaryAction.TryAgain,
            _ => PrimaryAction.None,
        };
        string label = primary switch
        {
            PrimaryAction.PairPhone => s["Primary_Pair"],
            PrimaryAction.StartEngine => s["Primary_Start"],
            PrimaryAction.FinishSetup => s["Primary_FinishSetup"],
            PrimaryAction.TryAgain => s["Primary_TryAgain"],
            PrimaryAction.Fix => problem!.FixLabel,
            _ => "",
        };
        return new DisplayInfo(state, Badge(state), state == DisplayState.Busy ? Eighths(fraction) : 0, tooltip, word, sub, primary, label, problem);
    }
}

/// <summary>The Needs-attention problems Bandroom can detect itself.</summary>
public static class Problems
{
    public static Problem NoFreePort(IStrings s) =>
        new(ProblemKind.NoFreePort, s["Port_Title"], s["Port_Why"], s["Action_Restart"], "Ports 8765–8775 in use.");

    /// <summary>The app was updated but its engine couldn't be: the previous one still runs. The fix tries again.</summary>
    public static Problem UpdateFailed(IStrings s, string details) =>
        new(ProblemKind.UpdateFailed, s["Update_Failed_Title"], s["Update_Failed_Why"], s["Primary_TryAgain"], details);

    public static Problem LowDisk(IStrings s, long freeBytes, string dataDir) =>
        new(ProblemKind.LowDisk, s["Disk_Title"], s.Format("Disk_Why", Health.HealthWords.GigabytesText(freeBytes, s.Culture)), s["Disk_Fix"],
            $"{dataDir}: {freeBytes / 1_000_000} MB free");

    /// <summary>
    /// Full-band scores need one more step: says which components are missing ("The soloist separator and the
    /// band writer aren't downloaded yet."); none named means Brasscribe's own tools. The details list the files, or
    /// say why setup stopped (<paramref name="stopped"/>) when it did.
    /// </summary>
    public static Problem MissingDownload(IStrings s, IReadOnlyList<ModelComponent> missing, IReadOnlyList<string>? files = null, string? stopped = null) =>
        new(ProblemKind.MissingDownload, s["Download_Title"], DownloadText.NotDownloaded(s, missing), s["Primary_FinishSetup"],
            stopped is not null ? "Setup stopped: " + stopped
            : files is { Count: > 0 } ? "Missing: " + string.Join(", ", files)
            : missing.Count > 0 ? "Missing: " + string.Join(", ", missing)
            : "The tool environments aren't installed.");

    /// <summary>The model download stopped: the macOS setup window's words for the reason, and its fix.</summary>
    public static Problem DownloadStopped(IStrings s, DownloadError error)
    {
        var (kind, prefix, fix) = error switch
        {
            DownloadError.KeyMissing => (ProblemKind.MissingDownload, "Setup_3_NoKey", s["Setup_3_NoKey_Fix"]),
            DownloadError.KeyRefused => (ProblemKind.KeyRefused, "Key", s["Key_Paste"]),
            DownloadError.LicenceNotAccepted => (ProblemKind.MissingDownload, "Setup_3_Licence", s["Setup_3_Licence_Fix"]),
            DownloadError.NotEnoughSpace => (ProblemKind.MissingDownload, "Setup_3_Space", s["Disk_Fix"]),
            DownloadError.ChecksumMismatch => (ProblemKind.MissingDownload, "Setup_3_Damaged", s["Primary_TryAgain"]),
            DownloadError.Disk => (ProblemKind.MissingDownload, "Setup_3_Disk", s["Primary_TryAgain"]),
            _ => (ProblemKind.MissingDownload, "Setup_3_Network", s["Primary_TryAgain"]),
        };
        string why = error switch
        {
            DownloadError.NotEnoughSpace n => s.Format("Setup_3_Space_Why", DownloadText.Gigabytes(n.NeededBytes, s.Culture), DownloadText.Gigabytes(n.FreeBytes, s.Culture)),
            DownloadError.Disk d => d.Message,
            _ => s[prefix + "_Why"],
        };
        return new(kind, s[prefix + "_Title"], why, fix, error.ToString());
    }
}

/// <summary>The words for the model downloads (design/server-app.md §10, download.why and setup.3).</summary>
public static class DownloadText
{
    /// <summary>"the soloist separator": the component inside a sentence.</summary>
    public static string ComponentName(IStrings s, ModelComponent c) => s[c switch
    {
        ModelComponent.SoloistSeparator => "Model_Soloist",
        ModelComponent.InstrumentSeparator => "Model_Instrument",
        _ => "Model_BandWriter",
    }];

    /// <summary>The setup list's item: "Band writer (MuScriptor)" is the one place the model is named (§3.2.1).</summary>
    public static string ComponentItem(IStrings s, ModelComponent c) => s[c switch
    {
        ModelComponent.SoloistSeparator => "Setup_Item_Soloist",
        ModelComponent.InstrumentSeparator => "Setup_Item_Separator",
        _ => "Setup_Item_BandWriter",
    }];

    /// <summary>"The band writer isn't downloaded yet." · "The soloist separator and the band writer aren't downloaded yet."</summary>
    public static string NotDownloaded(IStrings s, IReadOnlyList<ModelComponent> missing)
    {
        switch (missing.Count)
        {
            case 0: return s["Download_Why_Tools"];
            case 1:
                return s[missing[0] switch
                {
                    ModelComponent.SoloistSeparator => "Download_Why_Soloist",
                    ModelComponent.InstrumentSeparator => "Download_Why_Instrument",
                    _ => "Download_Why",
                }];
            default:
                var names = missing.Order().Select(c => ComponentName(s, c)).ToList();
                string list = s.Format("List_And", string.Join(", ", names.Take(names.Count - 1)), names[^1]);
                string sentence = s.Format("Download_Why_Many", list);
                return char.ToUpper(sentence[0], s.Culture) + sentence[1..];
        }
    }

    /// <summary>"Ready" · "Missing one download" · "Missing 2 downloads".</summary>
    public static string ReadyWord(IStrings s, int missing) => missing switch
    {
        0 => s["Health_Ready_Yes"],
        1 => s["Health_Ready_Missing"],
        _ => s.Format("Health_Ready_MissingMany", missing),
    };

    /// <summary>"3.1 of 9.8 GB · about 12 min left" while downloading, "Paused · 3.1 of 9.8 GB" when paused.</summary>
    public static string Progress(IStrings s, long done, long total, int? minutesLeft, bool paused)
    {
        string a = Gigabytes(done, s.Culture), b = Gigabytes(total, s.Culture);
        if (paused) return s.Format("Setup_3_Paused", a, b);
        return minutesLeft is { } m ? s.Format("Setup_3_Progress", a, b, m) : s.Format("Setup_3_Amount", a, b);
    }

    /// <summary>"1.4" (nb "1,4"): gigabytes with one decimal.</summary>
    public static string Gigabytes(long bytes, System.Globalization.CultureInfo culture) =>
        (bytes / 1_000_000_000.0).ToString("0.0", culture);
}
