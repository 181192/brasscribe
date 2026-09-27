using Brasscribe.Bandroom.Core.Supervisor;

namespace Brasscribe.Bandroom.Core.State;

/// <summary>What the icon, tooltip and status line say (design/server-app.md §6.1).</summary>
public enum DisplayState { SettingUp, Starting, Running, Busy, NeedsAttention, Stopped, Updating, Error }

/// <summary>The badge drawn on the mark: a shape per state, never colour alone.</summary>
public enum TrayBadge { None, DownArrow, Dots, Pie, Triangle, Square, CircularArrow, CrossCircle }

/// <summary>The one primary button of the flyout.</summary>
public enum PrimaryAction { None, PairPhone, StartEngine, FinishSetup, TryAgain, Fix }

public enum ProblemKind { NoFreePort, LowDisk, MissingDownload, FirewallBlocked, PublicNetwork, KeyRefused }

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
        double fraction = state == DisplayState.SettingUp ? i.SetupFraction : i.JobFraction ?? 0;
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
            DisplayState.Updating => s["Status_Updating_Sub"],
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

    public static Problem LowDisk(IStrings s, long freeBytes, string dataDir) =>
        new(ProblemKind.LowDisk, s["Disk_Title"], s.Format("Disk_Why", Health.HealthWords.GigabytesText(freeBytes, s.Culture)), s["Disk_Fix"],
            $"{dataDir}: {freeBytes / 1_000_000} MB free");

    public static Problem MissingDownload(IStrings s) =>
        new(ProblemKind.MissingDownload, s["Download_Title"], s["Download_Why"], s["Primary_FinishSetup"],
            "MuScriptor model missing under the models folder.");
}
