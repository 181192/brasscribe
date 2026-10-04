using System.Diagnostics;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.UIA3;

namespace Brasscribe.ScreenCheck;

/// <summary>
/// Bandroom for Windows' screen catalogue: every view with sample content (--show VIEW [--state STATE], no engine),
/// one start each, with --theme and --lang. For each window: a screenshot once it keeps still, the contrast of its
/// text (UI Automation says where the text is), and in the first theme of the English run the Axe.Windows rules and
/// the walk with Tab. A contrast theme and the text size are set for the whole run beforehand (ScreenCheck system).
/// </summary>
internal static class BandroomCatalogue
{
    public const string Views = "flyout,flyout:busy,flyout:attention,flyout:stopped,flyout:error,devices,confirm-stop,window,pair,allow,settings";

    public static int Run(Options o)
    {
        string exe = Path.GetFullPath(o.Need("exe"));
        string outDir = Path.GetFullPath(o.Need("out"));
        string run = o.Get("run") ?? "en";
        bool checks = o.Get("checks") != "0";
        string lang = run == "nb" ? "nb" : "en";
        string prefix = run is "en" or "contrast" ? "" : run + "-";
        Directory.CreateDirectory(outDir);
        var result = new CatalogueRun();
        var themes = o.List("themes", "light,dark");
        foreach (var theme in themes)
            foreach (var entry in o.List("scenes", Views))
            {
                var parts = entry.Split(':');
                string name = string.Join("-", parts);
                var args = new List<string> { "--show", parts[0], "--theme", theme, "--lang", lang };
                if (parts.Length > 1) args.AddRange(["--state", parts[1]]);
                try
                {
                    Show(exe, args, out var process, out var windows);
                    using (process)
                        try
                        {
                            for (int i = 0; i < windows.Count; i++)
                            {
                                string shot = $"{name}{(i == 0 ? "" : $"-{i}")}--{(run == "contrast" ? "contrast" : prefix + theme)}";
                                var (picture, steady) = Win.Steady(windows[i]);
                                Png.Save(Path.Combine(steady ? outDir : Path.Combine(outDir, "unsteady"), shot + ".png"), picture);
                                result.Shots.Add(shot);
                                if (!steady) result.Unsteady.Add(shot);
                                if (!checks) continue;
                                result.Findings.AddRange(Contrast.Check(shot, picture, Texts(windows[i])));
                                if (run == "en" && theme == themes[0])
                                {
                                    result.Findings.AddRange(Scan.Axe(process.Id, shot, Path.Combine(outDir, "scans", "axe")));
                                    result.Findings.AddRange(Scan.Keyboard(process.Id, windows[i], shot, out var order));
                                    Directory.CreateDirectory(Path.Combine(outDir, "scans"));
                                    File.WriteAllLines(Path.Combine(outDir, "scans", shot + ".tab.txt"), order);
                                }
                            }
                        }
                        finally
                        {
                            if (!process.HasExited) process.Kill(entireProcessTree: true);
                        }
                }
                catch (Exception e) when (e is not UsageException)
                {
                    result.Failed.Add($"{name} ({theme}): {e.Message}");
                    Console.Error.WriteLine($"{name} ({theme}): {e}");
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

    /// <summary>The window's text, where UI Automation puts it, in the window picture's pixels.</summary>
    private static List<ScreenText> Texts(nint hwnd)
    {
        using var automation = new UIA3Automation();
        var window = automation.FromHandle(hwnd);
        Win.GetWindowRect(hwnd, out var w);
        var found = new List<ScreenText>();
        foreach (var e in window.FindAllDescendants(cf => cf.ByControlType(ControlType.Text)))
        {
            try
            {
                var p = e.Properties;
                var r = e.BoundingRectangle;
                if (p.IsOffscreen.ValueOrDefault || r.IsEmpty || string.IsNullOrWhiteSpace(p.Name.ValueOrDefault)) continue;
                found.Add(new ScreenText(p.Name.Value.Trim(), new Box(r.X - w.Left, r.Y - w.Top, r.Width, r.Height), KindOf(e)));
            }
            catch (Exception x) when (x is System.Runtime.InteropServices.COMException or FlaUI.Core.Exceptions.PropertyNotSupportedException) { }
        }
        return found;
    }

    /// <summary>Large text by its font size and weight from the Text pattern; body text when the pattern does not say.</summary>
    private static TextKind KindOf(AutomationElement e)
    {
        try
        {
            if (e.Patterns.Text.PatternOrDefault?.DocumentRange is { } range
                && range.GetAttributeValue(e.Automation.TextAttributeLibrary.FontSize) is double points)
            {
                double px = points * 96 / 72;
                int weight = range.GetAttributeValue(e.Automation.TextAttributeLibrary.FontWeight) is int w ? w : 400;
                return ScreenText.KindOf(px, weight, null);
            }
        }
        catch (Exception x) when (x is System.Runtime.InteropServices.COMException or InvalidCastException) { }
        return TextKind.Normal;
    }
}
