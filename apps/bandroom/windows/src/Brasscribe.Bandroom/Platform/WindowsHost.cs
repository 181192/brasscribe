using System.Diagnostics;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using Brasscribe.Bandroom.Core.Health;
using Brasscribe.Bandroom.Core.Supervisor;
using Microsoft.Win32;

namespace Brasscribe.Bandroom.Platform;

/// <summary>CPU, memory and free space from the host (never from the engine), §3.6.</summary>
internal sealed class WindowsMetrics : IHostMetrics
{
    private readonly Lock _gate = new();
    private ulong _idle, _total;

    public double SampleCpuPercent()
    {
        if (!Native.GetSystemTimes(out var idle, out var kernel, out var user)) return 0;
        ulong i = idle.Value, t = kernel.Value + user.Value; // kernel time includes idle time
        lock (_gate)
        {
            bool first = _total == 0;
            // Counters that went backwards (or idle that grew more than the total) give no reading.
            bool valid = !first && i >= _idle && t > _total && i - _idle <= t - _total;
            ulong di = valid ? i - _idle : 0, dt = valid ? t - _total : 0;
            _idle = i;
            _total = t;
            return valid ? 100.0 * (dt - di) / dt : 0;
        }
    }

    public (ulong Total, ulong Available) Memory()
    {
        var m = new Native.MEMORYSTATUSEX { dwLength = (uint)Marshal.SizeOf<Native.MEMORYSTATUSEX>() };
        return Native.GlobalMemoryStatusEx(ref m) ? (m.ullTotalPhys, m.ullAvailPhys) : (0, 0);
    }

    public long FreeBytes(string path)
    {
        var root = Path.GetPathRoot(Path.GetFullPath(path));
        return root is null ? 0 : new DriveInfo(root).AvailableFreeSpace;
    }
}

internal static class Machine
{
    /// <summary>The device name people see in Settings › System › About (the DNS host name, case kept).</summary>
    public static string ComputerName()
    {
        int size = 0;
        Native.GetComputerNameEx(Native.ComputerNameDnsHostname, null, ref size);
        var sb = new System.Text.StringBuilder(size + 1);
        return size > 0 && Native.GetComputerNameEx(Native.ComputerNameDnsHostname, sb, ref size) && sb.Length > 0
            ? sb.ToString()
            : Environment.MachineName;
    }

    /// <summary>IPv4 addresses on Wi-Fi and Ethernet that are up, for the tech details.</summary>
    public static IReadOnlyList<string> LanAddresses()
    {
        try
        {
            return NetworkInterface.GetAllNetworkInterfaces()
                .Where(n => n.OperationalStatus == OperationalStatus.Up
                            && n.NetworkInterfaceType is NetworkInterfaceType.Ethernet or NetworkInterfaceType.Wireless80211 or NetworkInterfaceType.GigabitEthernet)
                .SelectMany(n => n.GetIPProperties().UnicastAddresses)
                .Where(a => a.Address.AddressFamily == AddressFamily.InterNetwork && !System.Net.IPAddress.IsLoopback(a.Address)
                            && !a.Address.ToString().StartsWith("169.254.", StringComparison.Ordinal))
                .Select(a => a.Address.ToString())
                .Distinct()
                .ToList();
        }
        catch (NetworkInformationException) { return []; }
    }

    /// <summary>Graphics adapters through DXGI: vendor id and user-mode driver version.</summary>
    public static IReadOnlyList<GpuAdapter> GraphicsAdapters()
    {
        var list = new List<GpuAdapter>();
        try
        {
            var iid = typeof(Native.IDXGIFactory1).GUID;
            if (Native.CreateDXGIFactory1(ref iid, out var factory) < 0) return list;
            var umd = new Guid("54ec77fa-1377-44e6-8c32-88fd5f44c84c"); // IDXGIDevice: asks for the UMD driver version
            for (uint i = 0; factory.EnumAdapters1(i, out var adapter) >= 0; i++)
            {
                if (adapter.GetDesc1(out var desc) < 0) continue;
                const uint software = 2;
                if ((desc.Flags & software) != 0) continue;
                Version? version = null;
                if (adapter.CheckInterfaceSupport(ref umd, out long v) >= 0)
                    version = new Version((int)(v >> 48) & 0xFFFF, (int)(v >> 32) & 0xFFFF, (int)(v >> 16) & 0xFFFF, (int)v & 0xFFFF);
                list.Add(new GpuAdapter(desc.Description, desc.VendorId, version));
                Marshal.ReleaseComObject(adapter);
            }
            Marshal.ReleaseComObject(factory);
        }
        catch (Exception e) when (e is COMException or DllNotFoundException or EntryPointNotFoundException or InvalidCastException) { }
        return list;
    }

    public static bool IsArm64 => RuntimeInformation.OSArchitecture == Architecture.Arm64;
}

/// <summary>
/// Run at sign-in. Packaged (MSIX): the <c>uap5:StartupTask</c> "BrasscribeBandroom", whose state the user can
/// change in Task Manager › Startup apps. Unpackaged: HKCU\…\Run, honouring Task Manager's
/// StartupApproved switch.
/// </summary>
internal sealed class StartupRegistration
{
    public const string TaskId = "BrasscribeBandroom";
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string ApprovedKey = @"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run";
    private const string ValueName = "Brasscribe Bandroom";

    public static bool IsPackaged
    {
        get
        {
            try { return Windows.ApplicationModel.Package.Current is not null; }
            catch (InvalidOperationException) { return false; }
            catch (COMException) { return false; }
        }
    }

    /// <summary>Whether it starts at sign-in now.</summary>
    public bool Enabled
    {
        get
        {
            if (IsPackaged)
            {
                var state = PackagedTask()?.State;
                return state is Windows.ApplicationModel.StartupTaskState.Enabled or Windows.ApplicationModel.StartupTaskState.EnabledByPolicy;
            }
            using var run = Registry.CurrentUser.OpenSubKey(RunKey);
            if (run?.GetValue(ValueName) is null) return false;
            using var approved = Registry.CurrentUser.OpenSubKey(ApprovedKey);
            // Task Manager writes 02 00… for enabled and 03 00… for disabled.
            return approved?.GetValue(ValueName) is not byte[] b || b.Length == 0 || (b[0] & 1) == 0;
        }
        set
        {
            if (IsPackaged)
            {
                var task = PackagedTask();
                if (task is null) return;
                // Windows may ask the user: never wait for that on the UI thread.
                if (value) _ = task.RequestEnableAsync();
                else task.Disable();
                return;
            }
            using var run = Registry.CurrentUser.CreateSubKey(RunKey);
            if (value) run.SetValue(ValueName, $"\"{Environment.ProcessPath}\" --background");
            else run.DeleteValue(ValueName, throwOnMissingValue: false);
            using var approved = Registry.CurrentUser.CreateSubKey(ApprovedKey);
            approved.DeleteValue(ValueName, throwOnMissingValue: false);
        }
    }

    /// <summary>False when policy or the user turned it off in Task Manager (a packaged app can't turn it back on itself).</summary>
    public bool Changeable => !IsPackaged || PackagedTask()?.State is not (Windows.ApplicationModel.StartupTaskState.DisabledByPolicy
        or Windows.ApplicationModel.StartupTaskState.EnabledByPolicy or Windows.ApplicationModel.StartupTaskState.DisabledByUser);

    private static Windows.ApplicationModel.StartupTask? PackagedTask()
    {
        try { return Windows.ApplicationModel.StartupTask.GetAsync(TaskId).AsTask().GetAwaiter().GetResult(); }
        catch (Exception e) when (e is COMException or ArgumentException or InvalidOperationException) { return null; }
    }
}

/// <summary>
/// Starts the engine inside a job object that kills the whole tree (pixi, python, adapters) when the job
/// closes: on Stop, on Restart and when Bandroom itself exits or crashes.
/// </summary>
internal sealed class JobObjectLauncher : IProcessLauncher, IDisposable
{
    private readonly SystemProcessLauncher _inner = new();
    private readonly IntPtr _job;

    public JobObjectLauncher()
    {
        _job = Native.CreateJobObject(IntPtr.Zero, null);
        var info = new Native.JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
        info.BasicLimitInformation.LimitFlags = Native.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        Native.SetInformationJobObject(_job, Native.JobObjectExtendedLimitInformation, ref info, Marshal.SizeOf(info));
    }

    public IEngineProcess Start(ProcessSpec spec, Action<string> output)
    {
        var p = _inner.Start(spec, output);
        try
        {
            using var proc = Process.GetProcessById(p.Id);
            Native.AssignProcessToJobObject(_job, proc.Handle);
        }
        catch (ArgumentException) { } // exited already
        catch (InvalidOperationException) { }
        return p;
    }

    public void Dispose() => Native.CloseHandle(_job);
}

/// <summary>Keeps the PC from idle-sleeping while a score is made; never blocks lid-close or a chosen sleep.</summary>
internal static class KeepAwake
{
    private static bool _on;

    public static void Set(bool on)
    {
        if (on == _on) return;
        _on = on;
        Native.SetThreadExecutionState(on ? Native.ES_CONTINUOUS | Native.ES_SYSTEM_REQUIRED : Native.ES_CONTINUOUS);
    }
}
