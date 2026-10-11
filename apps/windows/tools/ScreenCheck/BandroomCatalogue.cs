using System.Diagnostics;

namespace Brasscribe.ScreenCheck;

/// <summary>
/// Bandroom for Windows' screen catalogue: every view with sample content (--show VIEW [--state STATE], no engine),
/// one start each, with --theme and --lang. For each window: a screenshot once it is that window with its content
/// drawn and keeps still (<see cref="WindowShot"/>; otherwise the view is not taken), the contrast of its text (UI
/// Automation says where the text is), and in the first theme of the English run the Axe.Windows rules and the walk
/// with Tab. A contrast theme, the text size and animation effects off are set for the whole run beforehand
/// (ScreenCheck system).
/// </summary>
internal static class BandroomCatalogue
{
    public const string Views = "flyout,flyout:busy,flyout:attention,flyout:stopped,flyout:error,devices,confirm-stop,window,pair,allow,settings";

    public static int Run(Options o)
    {
        string exe = Path.GetFullPath(o.Need("exe"));
        string outDir = Path.GetFullPath(o.Need("out"));
        string run = o.Get("run") ?? "en";
        // "scan": Axe.Windows and the walk with Tab, no screenshots. A run of its own, after every screenshot: once a
        // Tab has been pressed, Windows draws keyboard focus rectangles in the windows started after it.
        bool scan = run == "scan";
        string lang = run == "nb" ? "nb" : "en";
        string prefix = run is "en" or "contrast" ? "" : run + "-";
        Directory.CreateDirectory(outDir);
        if (SystemState.AnimationsOn)
            throw new InvalidOperationException("Windows' animation effects are on: a view could be taken while it fades or slides in (ScreenCheck system --animations off)");
        var result = new CatalogueRun();
        var themes = o.List("themes", "light,dark");
        foreach (var theme in themes)
            foreach (var entry in o.List("scenes", Views))
            {
                var parts = entry.Split(':');
                string name = string.Join("-", parts);
                var args = new List<string> { "--show", parts[0], "--theme", theme, "--lang", lang };
                if (parts.Length > 1) args.AddRange(["--state", parts[1]]);
                // The screenshot's name: the view, its window when it has more than one, and the run's appearance.
                string Shot(int window) => $"{name}{(window == 0 ? "" : $"-{window}")}--{(run == "contrast" ? "contrast" : scan ? theme : prefix + theme)}";
                string shot = Shot(0);
                try
                {
                    Show(exe, args, out var process, out var windows);
                    using (process)
                        try
                        {
                            for (int i = 0; i < windows.Count; i++)
                            {
                                shot = Shot(i);
                                var taken = WindowShot.Take(process, windows[i], shot, notTaken: scan ? null : Path.Combine(outDir, "not-taken"));
                                var picture = taken.Picture!;
                                if (scan)
                                {
                                    result.Findings.AddRange(Scan.Axe(process.Id, shot, Path.Combine(outDir, "scans", "axe")));
                                    result.Findings.AddRange(Scan.Keyboard(process.Id, windows[i], shot, out var order));
                                    Directory.CreateDirectory(Path.Combine(outDir, "scans"));
                                    File.WriteAllLines(Path.Combine(outDir, "scans", shot + ".tab.txt"), order);
                                    continue;
                                }
                                Png.Save(Path.Combine(outDir, shot + ".png"), picture);
                                result.Shots.Add(shot);
                                result.Findings.AddRange(Contrast.Check(shot, picture, taken.Texts));
                            }
                        }
                        finally
                        {
                            if (!process.HasExited) process.Kill(entireProcessTree: true);
                        }
                }
                catch (Exception e) when (e is not UsageException)
                {
                    result.Failed.Add($"{shot}: {e.Message}");
                    Console.Error.WriteLine($"{shot}: {e}");
                }
                finally
                {
                    result.Save(Path.Combine(outDir, $"catalogue-bandroom-{run}.json"));
                }
            }
        Console.WriteLine($"{result.Shots.Count} screenshots, {result.Findings.Count} findings, {result.Failed.Count} views not taken");
        return 0;
    }

    private static void Show(string exe, List<string> args, out Process process, out List<nint> windows)
    {
        var psi = new ProcessStartInfo(exe) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(exe)! };
        foreach (var a in args) psi.ArgumentList.Add(a);
        process = Process.Start(psi) ?? throw new InvalidOperationException("Bandroom did not start");
        var deadline = DateTime.UtcNow.AddSeconds(90);
        windows = [];
        while (DateTime.UtcNow < deadline && !process.HasExited && (windows = Win.Visible(process.Id)).Count == 0) Thread.Sleep(500);
        if (process.HasExited) throw new InvalidOperationException($"Bandroom exited with code {process.ExitCode} before showing a window");
        if (windows.Count == 0) throw new TimeoutException("no window after 90 s");
        Thread.Sleep(1000);
        windows = Win.Visible(process.Id); // a view may open a second window after the first
    }
}
