using System.Diagnostics;

namespace Brasscribe.ScreenCheck;

/// <summary>
/// The Axe.Windows rules and the walk with Tab on every screen of Play for Windows, one start of the app each
/// (--show SCENE --theme light, sample content). The screenshots and the other checks are the catalogue's, taken in
/// one process (tests/Brasscribe.Play.Catalogue); these two run against the app's own build, since the app built as
/// the catalogue's test host ended (an access violation) while Axe.Windows read it. The findings are named after
/// the screenshot of the same screen in Light, and written as catalogue-scan.json next to the screenshots.
/// </summary>
internal static class PlayScan
{
    /// <summary>The computer in Play's sample scenes (PreviewScenes.SampleServer).</summary>
    private const string PreviewServer = "Studio PC";

    public const string Scenes = "first-run,home,home-offline,what-is-this,transcribing,review,review-listening,choose-output,score,part,export,error,settings";

    public static int Run(Options o)
    {
        string exe = Path.GetFullPath(o.Need("exe"));
        string score = Path.GetFullPath(o.Need("score"));
        string outDir = Path.GetFullPath(o.Need("out"));
        string scans = Path.Combine(outDir, "scans");
        Directory.CreateDirectory(scans);
        var result = new CatalogueRun();
        // First, before any other start of the app can add to its library: Pink chosen at start against Pink chosen in
        // Settings while the app runs (the catalogue's screenshots).
        if (o.Get("shots") is { } shots)
            foreach (var pink in new[] { "pink-light", "pink-dark" })
                ThemeAtStart(exe, score, Path.Combine(shots, $"home--{pink}.png"), pink, scans, result);
        foreach (var scene in o.List("scenes", Scenes))
        {
            string shot = $"{scene}--light";
            var psi = new ProcessStartInfo(exe) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(exe)! };
            foreach (var a in new[] { "--show", scene, "--theme", "light", "--score", score }) psi.ArgumentList.Add(a);
            Process? app = null;
            try
            {
                app = Process.Start(psi) ?? throw new InvalidOperationException("Play did not start");
                var deadline = DateTime.UtcNow.AddSeconds(90);
                while (app.MainWindowHandle == 0 && !app.HasExited && DateTime.UtcNow < deadline) { Thread.Sleep(500); app.Refresh(); }
                if (app.HasExited) throw new InvalidOperationException($"Play exited with code {app.ExitCode} before showing a window");
                if (app.MainWindowHandle == 0) throw new TimeoutException("no window after 90 s");
                if (scene is "export" or "settings") WaitForDialog(app.MainWindowHandle); // it opens 1.5 s after the screen
                WindowShot.Take(app, app.MainWindowHandle, shot + " (Axe.Windows and Tab)");
                result.Findings.AddRange(Scan.Axe(app.Id, shot, Path.Combine(scans, "axe")));
                result.Findings.AddRange(Scan.Keyboard(app.Id, app.MainWindowHandle, shot, out var order));
                File.WriteAllLines(Path.Combine(scans, shot + ".tab.txt"), order);
            }
            catch (Exception e) when (e is not UsageException)
            {
                result.Failed.Add($"{scene} (Axe.Windows and Tab): {e.Message}");
                Console.Error.WriteLine($"{scene}: {e}");
            }
            finally
            {
                if (app is { HasExited: false }) app.Kill(entireProcessTree: true);
                app?.Dispose();
                result.Save(Path.Combine(outDir, "catalogue-scan.json"));
            }
        }
        Language(exe, score, result);
        result.Save(Path.Combine(outDir, "catalogue-scan.json"));
        Console.WriteLine($"Axe.Windows and Tab on {o.List("scenes", Scenes).Length} screens: {result.Findings.Count} findings, {result.Failed.Count} not scanned");
        return 0;
    }

    /// <summary>
    /// Home started with --theme PINK looks as Home does after PINK was chosen in Settings while the app ran (the
    /// catalogue's <paramref name="switched"/> screenshot): a theme chosen at run time reaches every part of the window.
    /// </summary>
    private static void ThemeAtStart(string exe, string score, string switched, string theme, string scans, CatalogueRun result)
    {
        if (!File.Exists(switched)) { result.Failed.Add($"theme at start: no {Path.GetFileName(switched)} to compare with"); return; }
        var psi = new ProcessStartInfo(exe) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(exe)! };
        foreach (var a in new[] { "--show", "home", "--theme", theme, "--score", score }) psi.ArgumentList.Add(a);
        using var app = Process.Start(psi) ?? throw new InvalidOperationException("Play did not start");
        try
        {
            var deadline = DateTime.UtcNow.AddSeconds(90);
            while (app.MainWindowHandle == 0 && !app.HasExited && DateTime.UtcNow < deadline) { Thread.Sleep(500); app.Refresh(); }
            if (app.MainWindowHandle == 0) { result.Failed.Add($"theme at start: Play showed no window with --theme {theme}"); return; }
            string shot = $"home--{theme}";
            var atStart = WindowShot.Take(app, app.MainWindowHandle, shot + " (chosen at start)", client: true).Picture!;
            Png.Save(Path.Combine(scans, $"{shot}-at-start.png"), atStart);
            var (changed, diff) = ImageDiff.Of(Png.Load(switched), atStart);
            if (changed > ImageDiff.FloorPixels)
            {
                Png.Save(Path.Combine(scans, $"{shot}-at-start-diff.png"), diff);
                result.Findings.Add(new Finding(shot, "theme-at-start", "Home",
                    $"{changed} pixels differ between {theme} chosen at start and chosen in Settings (scans/{shot}-at-start-diff.png)"));
            }
        }
        catch (ScreenNotTakenException e)
        {
            result.Failed.Add($"theme at start ({theme}): {e.Message}");
        }
        finally
        {
            if (!app.HasExited) app.Kill(entireProcessTree: true);
        }
    }

    /// <summary>
    /// A dialog is open in the window: UI Automation shows a ContentDialog as a window (class Popup) inside it.
    /// </summary>
    private static void WaitForDialog(nint hwnd)
    {
        using var automation = new FlaUI.UIA3.UIA3Automation();
        var clock = Stopwatch.StartNew();
        while (clock.Elapsed < SteadyShot.Bound)
        {
            try
            {
                if (automation.FromHandle(hwnd).FindFirstDescendant(cf =>
                        cf.ByControlType(FlaUI.Core.Definitions.ControlType.Window).And(cf.ByClassName("Popup"))) is not null)
                    return;
            }
            catch (System.Runtime.InteropServices.COMException) { }
            Thread.Sleep(250);
        }
        throw new ScreenNotTakenException($"screen not taken: its dialog did not open in {SteadyShot.Bound.TotalSeconds:0} s");
    }

    /// <summary>
    /// The app's own build started in bokmål (--lang nb-NO, the value Settings › Language stores) names its Settings
    /// button «Innstillinger»: the language choice reaches the app.
    /// </summary>
    private static void Language(string exe, string score, CatalogueRun result)
    {
        var psi = new ProcessStartInfo(exe) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(exe)! };
        foreach (var a in new[] { "--show", "home", "--lang", "nb-NO", "--score", score }) psi.ArgumentList.Add(a);
        using var app = Process.Start(psi) ?? throw new InvalidOperationException("Play did not start");
        try
        {
            var deadline = DateTime.UtcNow.AddSeconds(90);
            while (app.MainWindowHandle == 0 && !app.HasExited && DateTime.UtcNow < deadline) { Thread.Sleep(500); app.Refresh(); }
            if (app.MainWindowHandle == 0) { result.Failed.Add("language: Play showed no window with --lang nb-NO"); return; }
            WindowShot.Take(app, app.MainWindowHandle, "home--nb (the language at start)");
            using var automation = new FlaUI.UIA3.UIA3Automation();
            var button = automation.FromHandle(app.MainWindowHandle).FindFirstDescendant(cf => cf.ByAutomationId("SettingsButton"));
            string name = button?.Properties.Name.ValueOrDefault ?? "(no Settings button)";
            if (name != "Innstillinger")
                result.Findings.Add(new Finding("home--nb", "language", "Button \"SettingsButton\"",
                    $"named \"{name}\" with --lang nb-NO, not «Innstillinger»: the app is not in bokmål"));
            // A string from code (the connection line, through App.Strings), not from the XAML.
            var connection = automation.FromHandle(app.MainWindowHandle).FindAllDescendants(cf => cf.ByControlType(FlaUI.Core.Definitions.ControlType.Text))
                .Select(t => t.Properties.Name.ValueOrDefault ?? "").FirstOrDefault(t => t.Contains(PreviewServer, StringComparison.Ordinal)) ?? "(no connection line)";
            if (!connection.StartsWith("Koblet til", StringComparison.Ordinal))
                result.Findings.Add(new Finding("home--nb", "language", "the connection line",
                    $"\"{connection}\" with --lang nb-NO: the strings from code are not in bokmål"));
        }
        catch (ScreenNotTakenException e)
        {
            result.Failed.Add($"language: {e.Message}");
        }
        finally
        {
            if (!app.HasExited) app.Kill(entireProcessTree: true);
        }
    }
}
