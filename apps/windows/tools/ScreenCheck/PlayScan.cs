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
                Thread.Sleep(scene is "export" or "settings" ? 2500 : 0); // the dialog opens 1.5 s after the screen
                Win.Steady(app.MainWindowHandle);
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
            Win.Steady(app.MainWindowHandle);
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
        finally
        {
            if (!app.HasExited) app.Kill(entireProcessTree: true);
        }
    }
}
