using System.Collections.ObjectModel;
using System.Globalization;
using System.Text;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.State;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Brasscribe.Bandroom.Core.ViewModels;

public enum FlyoutView { Main, Devices, Confirm }

public enum ConfirmKind { None, StopBusy, RestartBusy, RemoveDevice }

/// <summary>
/// The taskbar-corner flyout and the "Brasscribe on this PC" window (§7): header and status line, the job
/// being made, one primary button, Phones and tablets, This computer, Restart / Stop / Open Studio and the
/// tech disclosure. Sub-views (the device list, confirmations) replace the main view in place, Back first.
/// </summary>
public sealed partial class FlyoutViewModel : ObservableObject
{
    private readonly IStrings _s;
    private readonly IBandroomActions _actions;
    private readonly IAnnouncer _announcer;
    private readonly TimeProvider _time;
    private DisplayState? _lastState;
    private int _lastAnnouncedPercent = -100;
    private DateTimeOffset _lastAnnouncedAt;
    private bool _restartWhenDone;
    private DeviceRow? _removing;
    private BandroomSnapshot? _snapshot;

    public FlyoutViewModel(IStrings strings, IBandroomActions actions, IAnnouncer? announcer = null, TimeProvider? time = null)
    {
        _s = strings;
        _actions = actions;
        _announcer = announcer ?? new NullAnnouncer();
        _time = time ?? TimeProvider.System;
    }

    public IStrings Strings => _s;

    /// <summary>Asks the view to move keyboard focus: "Primary", "Back", "ConfirmTitle", "DevicesHeading", "Devices", "Row:N".</summary>
    public event Action<string>? FocusRequested;

    // ----- Labels that don't change with the state -----
    public string MoreLabel => _s["More"];
    public string NowHeading => _s["Now_Heading"];
    public string DevicesHeading => _s["Devices_Heading"];
    public string ComputerHeading => _s["Computer_Heading"];
    public string LoadLabel => _s["Health_Load"];
    public string MemoryLabel => _s["Health_Memory"];
    public string DiskLabel => _s["Health_Disk"];
    public string ReadyLabel => _s["Health_Ready"];
    public string RestartLabel => _s["Action_Restart"];
    public string StopLabel => _s["Action_Stop"];
    public string OpenStudioLabel => _s["Action_OpenStudio"];
    public string TechSummary => _s["Tech_Summary"];
    public string ShowLogsLabel => _s["Tech_Logs"];
    public string CopyLabel => _s["Tech_Copy"];
    public string BackLabel => _s["Back"];
    public string PairLabel => _s["Primary_Pair"];
    public string EmptyDevicesText => _s["Devices_Empty"];
    public string RemoveLabel => _s["Devices_Remove"];

    // ----- State -----
    [ObservableProperty] public partial DisplayState State { get; set; } = DisplayState.Starting;
    [ObservableProperty] public partial TrayBadge Badge { get; set; } = TrayBadge.Dots;
    [ObservableProperty] public partial int PieEighths { get; set; }
    [ObservableProperty] public partial string Header { get; set; } = "";
    [ObservableProperty] public partial string StatusWord { get; set; } = "";
    [ObservableProperty] public partial string StatusSub { get; set; } = "";
    [ObservableProperty] public partial string Tooltip { get; set; } = "";
    [ObservableProperty] public partial string PrimaryLabel { get; set; } = "";
    [ObservableProperty] public partial bool HasPrimary { get; set; }
    [ObservableProperty] public partial bool PrimaryIsPair { get; set; }
    [ObservableProperty] public partial bool CanRestart { get; set; }
    [ObservableProperty] public partial bool CanStop { get; set; }

    // ----- Now -----
    [ObservableProperty] public partial bool IsBusy { get; set; }
    [ObservableProperty] public partial string JobStep { get; set; } = "";
    [ObservableProperty] public partial string JobSource { get; set; } = "";
    [ObservableProperty] public partial double JobPercent { get; set; }
    [ObservableProperty] public partial string JobProgressText { get; set; } = "";
    [ObservableProperty] public partial string QueueText { get; set; } = "";
    [ObservableProperty] public partial bool HasQueue { get; set; }

    // ----- Phones and tablets -----
    [ObservableProperty] public partial string DevicesSummary { get; set; } = "";
    public ObservableCollection<DeviceRow> Devices { get; } = [];
    [ObservableProperty] public partial bool HasDevices { get; set; }

    // ----- This computer -----
    [ObservableProperty] public partial bool HasHealth { get; set; }
    [ObservableProperty] public partial string LoadWord { get; set; } = "";
    [ObservableProperty] public partial int LoadLevel { get; set; }
    [ObservableProperty] public partial string MemoryWord { get; set; } = "";
    [ObservableProperty] public partial int MemoryLevel { get; set; }
    [ObservableProperty] public partial string DiskText { get; set; } = "";
    [ObservableProperty] public partial string ReadyWord { get; set; } = "";
    [ObservableProperty] public partial bool IsReady { get; set; }
    [ObservableProperty] public partial string SpeedCaption { get; set; } = "";
    [ObservableProperty] public partial string TechText { get; set; } = "";

    // ----- Sub-views -----
    [ObservableProperty] public partial FlyoutView View { get; set; } = FlyoutView.Main;
    [ObservableProperty] public partial ConfirmKind Confirm { get; set; }
    [ObservableProperty] public partial string ConfirmTitle { get; set; } = "";
    [ObservableProperty] public partial string ConfirmBody { get; set; } = "";
    [ObservableProperty] public partial string ConfirmPrimaryLabel { get; set; } = "";
    [ObservableProperty] public partial string ConfirmSecondaryLabel { get; set; } = "";
    [ObservableProperty] public partial string ConfirmTertiaryLabel { get; set; } = "";
    [ObservableProperty] public partial bool HasConfirmTertiary { get; set; }

    public bool IsMainView => View == FlyoutView.Main;
    public bool IsDevicesView => View == FlyoutView.Devices;
    public bool IsConfirmView => View == FlyoutView.Confirm;
    public bool HasNoDevices => !HasDevices;

    partial void OnViewChanged(FlyoutView value)
    {
        OnPropertyChanged(nameof(IsMainView));
        OnPropertyChanged(nameof(IsDevicesView));
        OnPropertyChanged(nameof(IsConfirmView));
    }

    partial void OnHasDevicesChanged(bool value) => OnPropertyChanged(nameof(HasNoDevices));

    /// <summary>Takes a new reading. Announces a state change once, and job progress at most every 10 s or 10 %.</summary>
    public void Apply(BandroomSnapshot snap)
    {
        _snapshot = snap;
        var info = StateRules.Describe(snap.Inputs, _s);
        State = info.State;
        Badge = info.Badge;
        PieEighths = info.PieEighths;
        Header = snap.Header;
        StatusWord = info.StatusWord;
        Tooltip = info.Tooltip;
        PrimaryLabel = info.PrimaryLabel;
        HasPrimary = info.Primary != PrimaryAction.None;
        PrimaryIsPair = info.Primary == PrimaryAction.PairPhone;
        CanRestart = snap.Inputs.Engine is Supervisor.EngineState.Running or Supervisor.EngineState.Starting or Supervisor.EngineState.Error;
        CanStop = snap.Inputs.Engine is Supervisor.EngineState.Running or Supervisor.EngineState.Starting;

        var job = info.State is DisplayState.Busy or DisplayState.NeedsAttention ? snap.Job : null;
        IsBusy = job is not null;
        StatusSub = job is null && info.State == DisplayState.Running ? info.StatusSub : info.State == DisplayState.Running ? "" : info.StatusSub;
        if (job is not null)
        {
            int pct = StateRules.Percent(job.Fraction);
            JobStep = _s[job.StepKey];
            JobSource = job.Title is { Length: > 0 } t ? _s.Format("Now_Title", t) : "";
            JobPercent = pct;
            JobProgressText = job.MinutesLeft is { } m ? _s.Format("Now_Progress", pct, m) : _s.Format("Now_Percent", pct);
            int queued = snap.Status?.JobsQueued ?? 0;
            HasQueue = queued > 0;
            QueueText = HasQueue ? _s.Format("Now_Queue", queued) : "";
            var now = _time.GetUtcNow();
            if (Math.Abs(pct - _lastAnnouncedPercent) >= 10 || now - _lastAnnouncedAt >= TimeSpan.FromSeconds(10))
            {
                if (_lastState == DisplayState.Busy) _announcer.Announce(JobStep + ", " + JobProgressText);
                _lastAnnouncedPercent = pct;
                _lastAnnouncedAt = now;
            }
        }
        else
        {
            JobStep = JobSource = JobProgressText = QueueText = "";
            HasQueue = false;
            _lastAnnouncedPercent = -100;
        }

        if (snap.Status is { } st) DevicesSummary = DeviceText.Summary(st.OnlineDevices, st.PairedDevices, _s);
        else DevicesSummary = "";

        if (snap.Health is { } h)
        {
            HasHealth = true;
            LoadLevel = (int)h.Load;
            LoadWord = _s[HealthWords.LoadKey(h.Load)];
            MemoryLevel = (int)h.Memory;
            MemoryWord = _s[HealthWords.MemoryKey(h.Memory)];
            DiskText = _s.Format("Health_Disk_Value", HealthWords.Gigabytes(h.FreeBytes));
            IsReady = h.ModelsReady;
            ReadyWord = h.ModelsReady ? _s["Health_Ready_Yes"] : _s["Health_Ready_Missing"];
        }
        else HasHealth = false;
        SpeedCaption = _s[snap.SpeedKey];
        TechText = FormatTech(snap.Tech);

        if (_lastState is { } last && last != info.State)
            _announcer.Announce(info.Problem is { } p ? StatusWord + ": " + p.Title : StatusWord);
        _lastState = info.State;

        if (_restartWhenDone && info.State != DisplayState.Busy && snap.Inputs.Engine == Supervisor.EngineState.Running)
        {
            _restartWhenDone = false;
            _ = _actions.RestartAsync();
        }
    }

    public void ApplyDevices(IReadOnlyList<DeviceInfo> devices, DateTimeOffset now)
    {
        var rows = DeviceText.Rows(devices, now, _s);
        Devices.Clear();
        foreach (var r in rows) Devices.Add(r);
        HasDevices = Devices.Count > 0;
        // Engines without /v1/status: the summary comes from the list itself.
        if (_snapshot?.Status is null && devices.Count > 0)
            DevicesSummary = DeviceText.Summary(rows.Count(r => r.IsOnline), rows.Count, _s);
    }

    public string FormatTech(TechDetails t)
    {
        var inv = CultureInfo.InvariantCulture;
        var sb = new StringBuilder();
        string pad(string label) => label.PadRight(10);
        sb.Append(pad(_s["Tech_Address"])).AppendLine(t.Addresses.Count > 0 ? string.Join(", ", t.Addresses) : "–");
        sb.Append(pad(_s["Tech_Port"])).AppendLine(t.Port?.ToString(inv) ?? "–");
        sb.Append(pad(_s["Tech_Version"])).AppendLine(t.Version);
        sb.Append(pad(_s["Tech_Device"])).AppendLine(t.RunsOn);
        sb.Append(pad(_s["Tech_Server"])).AppendLine(t.ServerId is { Length: > 0 } id ? id[..Math.Min(8, id.Length)] + "…" : "–");
        sb.Append(pad(_s["Tech_Data"])).Append(t.DataDir);
        return sb.ToString();
    }

    // ----- Commands -----

    [RelayCommand]
    private async Task PrimaryAsync()
    {
        var info = _snapshot is null ? null : StateRules.Describe(_snapshot.Inputs, _s);
        switch (info?.Primary)
        {
            case PrimaryAction.PairPhone: _actions.OpenPairWindow(); break;
            case PrimaryAction.StartEngine:
            case PrimaryAction.TryAgain: await _actions.StartAsync(); break;
            case PrimaryAction.FinishSetup: _actions.FinishSetup(); break;
            case PrimaryAction.Fix when info.Problem is { } p:
                if (p.Kind == ProblemKind.NoFreePort) await _actions.RestartAsync();
                else _actions.Fix(p.Kind);
                break;
        }
    }

    [RelayCommand] private void Pair() => _actions.OpenPairWindow();

    [RelayCommand]
    private async Task RestartAsync()
    {
        if (IsBusy) { ShowConfirm(ConfirmKind.RestartBusy); return; }
        await _actions.RestartAsync();
    }

    [RelayCommand]
    private async Task StopAsync()
    {
        if (IsBusy) { ShowConfirm(ConfirmKind.StopBusy); return; }
        await _actions.StopAsync();
    }

    [RelayCommand] private void OpenStudio() => _actions.OpenStudio();
    [RelayCommand] private void ShowLogs() => _actions.ShowLogs();

    [RelayCommand]
    private void CopyDiagnostics()
    {
        var sb = new StringBuilder();
        sb.AppendLine(Header).AppendLine(StatusWord);
        if (_snapshot is { } s) sb.AppendLine(FormatTech(s.Tech));
        _actions.CopyText(sb.ToString());
        _announcer.Announce(_s["Tech_Copied"]);
    }

    [RelayCommand]
    private void ShowDevices()
    {
        View = FlyoutView.Devices;
        FocusRequested?.Invoke("Back");
    }

    [RelayCommand]
    private void Back()
    {
        var from = View;
        var kind = Confirm;
        View = kind == ConfirmKind.RemoveDevice && from == FlyoutView.Confirm ? FlyoutView.Devices : FlyoutView.Main;
        Confirm = ConfirmKind.None;
        FocusRequested?.Invoke(View == FlyoutView.Devices ? "Devices" : from == FlyoutView.Devices ? "DevicesRow" : "Primary");
    }

    [RelayCommand]
    private void RemoveDevice(DeviceRow row)
    {
        _removing = row;
        ShowConfirm(ConfirmKind.RemoveDevice);
    }

    private void ShowConfirm(ConfirmKind kind)
    {
        string? title = _snapshot?.Job?.Title;
        Confirm = kind;
        HasConfirmTertiary = false;
        ConfirmTertiaryLabel = "";
        switch (kind)
        {
            case ConfirmKind.StopBusy:
                ConfirmTitle = title is { Length: > 0 } ? _s.Format("Stop_Busy_Title", title) : _s["Stop_Busy_Title_Untitled"];
                ConfirmBody = _s["Stop_Busy_Body"];
                ConfirmPrimaryLabel = _s["Stop_Busy_Stop"];
                ConfirmSecondaryLabel = _s["Stop_Busy_Keep"];
                break;
            case ConfirmKind.RestartBusy:
                ConfirmTitle = title is { Length: > 0 } ? _s.Format("Restart_Busy_Title", title) : _s["Restart_Busy_Title_Untitled"];
                ConfirmBody = "";
                ConfirmPrimaryLabel = _s["Restart_Busy_Later"];
                ConfirmSecondaryLabel = _s["Cancel"];
                ConfirmTertiaryLabel = _s["Restart_Busy_Now"];
                HasConfirmTertiary = true;
                break;
            case ConfirmKind.RemoveDevice:
                ConfirmTitle = _s.Format("RemoveDevice_Title", _removing?.Name);
                ConfirmBody = _s["RemoveDevice_Body"];
                ConfirmPrimaryLabel = _s["RemoveDevice_Ok"];
                ConfirmSecondaryLabel = _s["Cancel"];
                break;
        }
        View = FlyoutView.Confirm;
        FocusRequested?.Invoke("ConfirmTitle");
    }

    /// <summary>The confirmation's primary: Stop now, Restart when done, or Remove.</summary>
    [RelayCommand]
    private async Task ConfirmPrimaryAsync()
    {
        var kind = Confirm;
        switch (kind)
        {
            case ConfirmKind.StopBusy:
                Back();
                await _actions.StopAsync();
                break;
            case ConfirmKind.RestartBusy:
                _restartWhenDone = true;
                Back();
                break;
            case ConfirmKind.RemoveDevice when _removing is { } row:
                int index = Devices.IndexOf(row);
                await _actions.RemoveDeviceAsync(row.Id);
                Devices.Remove(row);
                HasDevices = Devices.Count > 0;
                _announcer.Announce(_s.Format("Devices_Removed", row.Name));
                _removing = null;
                Confirm = ConfirmKind.None;
                View = FlyoutView.Devices;
                // Focus the next row, or the heading when the list is now empty (§8).
                FocusRequested?.Invoke(Devices.Count == 0 ? "DevicesHeading" : "Row:" + Math.Min(index, Devices.Count - 1));
                break;
        }
    }

    /// <summary>Restart now (restart confirmation only).</summary>
    [RelayCommand]
    private async Task ConfirmTertiaryAsync()
    {
        Back();
        await _actions.RestartAsync();
    }

    /// <summary>Keep going / Cancel.</summary>
    [RelayCommand]
    private void ConfirmCancel()
    {
        _removing = null;
        Back();
    }

    /// <summary>Esc: a sub-view goes back first; returns true when the panel itself should close.</summary>
    public bool Escape()
    {
        if (View == FlyoutView.Main) return true;
        ConfirmCancel();
        return false;
    }

    public bool RestartPending => _restartWhenDone;
}
