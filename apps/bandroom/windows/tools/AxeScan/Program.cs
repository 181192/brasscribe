using System.Diagnostics;
using System.Runtime.InteropServices;
using Axe.Windows.Automation;
using Axe.Windows.Automation.Data;

// Usage: AxeScan <path to BrasscribeBandroom.exe> <output dir> <scene>...
// Each scene starts Bandroom with sample content (--show <scene>: flyout, devices, confirm-stop, window,
// pair, allow), waits for a visible window of the process (the flyout is a tool window, so
// Process.MainWindowHandle can't be trusted), scans it with Axe.Windows and writes an .a11ytest file.
// Exit code 1 when any rule fails, so CI can gate on it.
if (args.Length < 3)
{
    Console.Error.WriteLine("usage: AxeScan <exe> <output dir> <scene>...");
    return 2;
}

string exe = Path.GetFullPath(args[0]);
string outDir = Path.GetFullPath(args[1]);
Directory.CreateDirectory(outDir);

int failures = 0;
foreach (var scene in args.Skip(2))
{
    var psi = new ProcessStartInfo(exe) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(exe)! };
    foreach (var a in new[] { "--show", scene, "--theme", "light" }) psi.ArgumentList.Add(a);
    using var app = Process.Start(psi) ?? throw new InvalidOperationException("could not start " + exe);
    try
    {
        var deadline = DateTime.UtcNow.AddSeconds(90);
        while (Windows.Visible(app.Id).Count == 0 && DateTime.UtcNow < deadline && !app.HasExited) Thread.Sleep(500);
        if (app.HasExited) throw new InvalidOperationException($"[{scene}] the app exited with code {app.ExitCode} before showing a window");
        if (Windows.Visible(app.Id).Count == 0) throw new TimeoutException($"[{scene}] no window after 90 s");
        Thread.Sleep(4000); // let the view settle (the QR, the Allow card)

        var config = Config.Builder.ForProcessId(app.Id)
            .WithOutputDirectory(outDir)
            .WithOutputFileFormat(OutputFileFormat.A11yTest)
            .WithAlwaysSaveTestFile()
            .Build();
        var output = ScannerFactory.CreateScanner(config).Scan(new ScanOptions(scanId: scene));
        foreach (var window in output.WindowScanOutputs)
        {
            Console.WriteLine($"[{scene}] {window.ErrorCount} errors; results in {window.OutputFile.A11yTest}");
            foreach (var e in window.Errors)
            {
                var props = e.Element.Properties;
                string name = props is not null && props.TryGetValue("Name", out var n) ? n : "";
                string type = props is not null && props.TryGetValue("ControlType", out var t) ? t : "";
                Console.WriteLine($"  {e.Rule.ID}: {e.Rule.Description} | {type} \"{name}\"");
            }
            failures += window.ErrorCount;
        }
    }
    finally
    {
        if (!app.HasExited) app.Kill(entireProcessTree: true);
    }
}
Console.WriteLine($"total accessibility errors: {failures}");
return failures > 0 ? 1 : 0;

internal static class Windows
{
    private delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumProc proc, IntPtr lParam);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);

    public static List<IntPtr> Visible(int pid)
    {
        var list = new List<IntPtr>();
        EnumWindows((h, _) =>
        {
            GetWindowThreadProcessId(h, out uint p);
            if (p == pid && IsWindowVisible(h)) list.Add(h);
            return true;
        }, IntPtr.Zero);
        return list;
    }
}
