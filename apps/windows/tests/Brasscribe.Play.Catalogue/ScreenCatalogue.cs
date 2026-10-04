using System.Diagnostics;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;
using Brasscribe.ScreenCheck;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Microsoft.VisualStudio.TestTools.UnitTesting.AppContainer;

namespace Brasscribe.Play.Catalogue;

/// <summary>
/// Every screen of the app with sample content (the scenes of <see cref="PreviewScenes"/>, Settings and Share or
/// print), each in the Appearance choices this run asks for, switched while the screen is open, as a person does
/// in Settings. For each: a screenshot of the window as it is on screen, the contrast of every
/// text and icon measured on it, and text cut off. Axe.Windows and the walk with Tab run on the app's own build
/// (tools/ScreenCheck play). One process per language, contrast theme and text size: the runner script sets
/// those before it starts (tools/Screenshots/catalogue.ps1).
/// </summary>
[TestClass]
public sealed class ScreenCatalogue
{
    internal static App App = null!;

    /// <summary>The screens: the preview scenes, then two dialogs.</summary>
    public static IEnumerable<object[]> Screens =>
        PreviewScenes.Names.Append("settings").Where(Options.Wanted).Select(s => new object[] { s });

    private static readonly CatalogueRun Run = new();

    [UITestMethod]
    [DynamicData(nameof(Screens))]
    public async Task Screen(string scene)
    {
        Directory.CreateDirectory(Options.Out);
        var store = new InMemorySettings();
        store.Set(AppearanceSetting.Key, AppearanceSetting.Serialise(Options.Variants[0]));
        store.Set(AppearanceSetting.PinkUnlockedKey, true);
        store.Set(nameof(SettingsViewModel.ReduceMotion), true);
        string work = Path.Combine(Path.GetTempPath(), "brasscribe-catalogue", Guid.NewGuid().ToString("N"));
        long crashes = CrashLogLength();
        var (main, settings) = App.Compose(store, work, forcedTheme: null);
        var window = App.MainWindowInstance!;
        window.HeartbeatEnabled = false;
        window.Activate();
        try
        {
            bool dialog = scene is "export" or "settings";
            PreviewScenes.Show(main, scene == "settings" ? "home" : scene, Options.Score);
            var root = await LoadedAsync(window);
            if (Options.Contrast && !settings.HighContrast)
                throw new InvalidOperationException("the contrast theme is not on, so nothing in this run shows it");
            CheckLanguage();

            Picture? first = null;
            foreach (var variant in Options.Variants)
            {
                settings.Appearance = variant;
                if (dialog)
                {
                    // Opened in each choice, so it shows that choice (a person changes it in the dialog itself).
                    await SteadyAsync(root);
                    _ = scene == "export" ? window.ShowExportAsync() : window.OpenSettingsAsync();
                }
                var (picture, steady) = await SteadyAsync(root);
                if (Options.Contrast && first is not null)
                {
                    // A contrast theme always wins: every choice must look the same as the first (but in Settings,
                    // whose Appearance box shows the choice).
                    if (scene != "settings" && !picture.SameAs(first) && ImageDiff.Of(first, picture).Changed > ImageDiff.FloorPixels)
                        Run.Findings.Add(new Finding(ShotName(scene, Options.Variants[0]), "contrast-theme",
                            AppearanceSetting.Serialise(variant), "this Appearance choice changed the screen under a contrast theme"));
                }
                else
                {
                    first ??= picture;
                    string shot = ShotName(scene, variant);
                    Save(Path.Combine(steady ? Options.Out : Options.UnsteadyOut, shot + ".png"), picture);
                    Run.Shots.Add(shot);
                    if (!steady) Run.Unsteady.Add(shot);
                    if (Options.Checks) Run.Findings.AddRange(Contrast.Check(shot, picture, Texts(root, picture)));
                }
                if (dialog) await CloseDialogsAsync(window);
            }
        }
        catch (Exception e)
        {
            Run.Failed.Add($"{scene}: {e.GetType().Name}: {e.Message}");
            throw;
        }
        finally
        {
            await CloseDialogsAsync(window);
            // The Pink palette is merged into the app's resources while Pink is chosen: out again before the next
            // screen's window, which has a theme controller of its own.
            settings.Appearance = Appearance.System;
            window.Close();
            await Task.Delay(300);
            CheckCrashLog(scene, crashes);
            Save();
        }
    }

    /// <summary>The app's crash.log (App.WriteCrash): an exception nothing caught while this screen was open.</summary>
    private static readonly string CrashLog = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Brasscribe", "Play", "crash.log");

    private static long CrashLogLength() => File.Exists(CrashLog) ? new FileInfo(CrashLog).Length : 0;

    private static void CheckCrashLog(string scene, long before)
    {
        if (CrashLogLength() <= before) return;
        using var stream = new FileStream(CrashLog, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        stream.Position = before;
        string added = new StreamReader(stream).ReadToEnd();
        Console.WriteLine($"crash.log while {scene} was open:\n{added}");
        string first = added.Split('\n', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault()?.Trim() ?? "";
        // The line is "<time> <exception>: <message>"; the time is left out so the finding is the same in every run.
        Run.Findings.Add(new Finding($"{scene}--{Options.Prefix}any", "crash", first.Contains(' ') ? first[(first.IndexOf(' ') + 1)..] : first,
            "an exception nothing caught (crash.log); the app said \"Something went wrong\""));
    }

    [ClassCleanup]
    public static void Done() => Save();

    private static void Save()
    {
        Directory.CreateDirectory(Options.Out);
        Run.Save(Path.Combine(Options.Out, $"catalogue-{Options.Run}.json"));
    }

    private static string ShotName(string scene, Appearance variant) =>
        Options.Contrast ? $"{scene}--contrast" : $"{scene}--{Options.Prefix}{AppearanceSetting.Serialise(variant)}";

    // ---- the window ----

    private static async Task<FrameworkElement> LoadedAsync(MainWindow window)
    {
        var deadline = DateTime.UtcNow.AddSeconds(30);
        while (DateTime.UtcNow < deadline)
        {
            if (window.Content is FrameworkElement { IsLoaded: true, XamlRoot: not null } root) return root;
            await Task.Delay(100);
        }
        throw new TimeoutException("the window's content did not load in 30 s");
    }

    /// <summary>
    /// The screen once it keeps still: pictures 250 ms apart until six in a row are the same (1.5 s), or 20 s pass
    /// (then it is not steady: something on it moves, and its screenshot is kept but not compared).
    /// </summary>
    private static async Task<(Picture Picture, bool Steady)> SteadyAsync(FrameworkElement root)
    {
        var start = Stopwatch.StartNew();
        Picture? last = null;
        int same = 0;
        while (start.Elapsed < TimeSpan.FromSeconds(20))
        {
            await Task.Delay(250);
            var now = await CaptureAsync(root);
            same = last is not null && now.SameAs(last) ? same + 1 : 0;
            last = now;
            if (same >= 5) return (now, true);
        }
        return (last!, false);
    }

    /// <summary>
    /// The window's client area as it is on screen, open dialogs and their dimming included (PrintWindow, from a
    /// thread of its own so this one goes on answering). RenderTargetBitmap drew an open ContentDialog half
    /// transparent, as at the start of its opening animation, and without the dimming behind it.
    /// </summary>
    private static Task<Picture> CaptureAsync(FrameworkElement root)
    {
        nint hwnd = WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowInstance!);
        return Task.Run(() => Gdi.CaptureClient(hwnd));
    }

    private static async Task CloseDialogsAsync(MainWindow window)
    {
        if (window.Content?.XamlRoot is not { } xamlRoot) return;
        bool any = false;
        foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(xamlRoot))
            if (popup.Child is ContentDialog d) { d.Hide(); any = true; }
        if (any) await Task.Delay(500); // its closing animation, before the next one opens
    }

    /// <summary>The run in bokmål shows the app in bokmål: the language reaches the app's strings.</summary>
    private static void CheckLanguage()
    {
        if (Options.Run != "nb" || Run.Findings.Any(f => f.Check == "language")) return;
        string said = App.Strings["Pink_Unlocked"];
        if (said != "🎺 Rosa låst opp")
            Run.Findings.Add(new Finding("all", "language", "App.Strings[\"Pink_Unlocked\"]",
                $"\"{said}\" in the bokmål run (languages: {string.Join(", ", Microsoft.Windows.Globalization.ApplicationLanguages.Languages)}; " +
                $"override: {Microsoft.Windows.Globalization.ApplicationLanguages.PrimaryLanguageOverride})"));
    }

    // ---- text on screen ----

    /// <summary>
    /// Every text and icon a person sees: visible, not in a disabled control (WCAG leaves those out), clipped to the
    /// parts that scroll. While a dialog is open only its own (the window behind it is dimmed).
    /// </summary>
    private static List<ScreenText> Texts(FrameworkElement root, Picture picture)
    {
        double scale = root.XamlRoot.RasterizationScale;
        var popups = VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).Select(p => p.Child).OfType<FrameworkElement>().ToList();
        var scopes = popups.Any(p => p is ContentDialog) ? popups : popups.Prepend(root).ToList();
        var found = new List<ScreenText>();
        foreach (var scope in scopes) Walk(scope, scale, picture, found);
        return found.DistinctBy(t => (t.Box, t.Kind)).ToList();
    }

    private static void Walk(DependencyObject node, double scale, Picture picture, List<ScreenText> found)
    {
        if (node is UIElement { Visibility: not Visibility.Visible } or UIElement { Opacity: < 0.01 }) return;
        if (node is Control { IsEnabled: false }) return;
        if (node is FrameworkElement { ActualWidth: > 0, ActualHeight: > 0 } element)
        {
            ScreenText? text = element switch
            {
                TextBlock tb when !string.IsNullOrWhiteSpace(tb.Text) => new ScreenText(tb.Text.Trim(), default,
                    ScreenText.KindOf(tb.FontSize, tb.FontWeight.Weight, tb.FontFamily?.Source), tb.IsTextTrimmed),
                FontIcon icon when !string.IsNullOrEmpty(icon.Glyph) => new ScreenText(icon.Glyph, default, TextKind.Icon),
                _ => null,
            };
            if (text is not null && BoxOf(element, scale, picture) is { IsEmpty: false } box) found.Add(text with { Box = box });
            if (element is FontIcon) return;
        }
        for (int i = 0, n = VisualTreeHelper.GetChildrenCount(node); i < n; i++) Walk(VisualTreeHelper.GetChild(node, i), scale, picture, found);
    }

    /// <summary>Where an element is in the picture, cut to every part above it that scrolls; empty when out of view.</summary>
    private static Box BoxOf(FrameworkElement element, double scale, Picture picture)
    {
        var r = element.TransformToVisual(null).TransformBounds(new Windows.Foundation.Rect(0, 0, element.ActualWidth, element.ActualHeight));
        for (var up = VisualTreeHelper.GetParent(element); up is not null; up = VisualTreeHelper.GetParent(up))
        {
            if (up is not ScrollViewer and not Microsoft.UI.Xaml.Controls.Primitives.ScrollPresenter) continue;
            var v = (FrameworkElement)up;
            var view = v.TransformToVisual(null).TransformBounds(new Windows.Foundation.Rect(0, 0, v.ActualWidth, v.ActualHeight));
            r.Intersect(view);
            if (r.IsEmpty) return default;
        }
        return Box.FromDips(r.X, r.Y, r.Width, r.Height, scale).Within(picture.Width, picture.Height);
    }

    // ---- files ----

    private static void Save(string path, Picture picture)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        Png.Save(path, picture);
    }

    /// <summary>This run's settings, from the environment (the test platform has the command line).</summary>
    private static class Options
    {
        private static string? Env(string name) => Environment.GetEnvironmentVariable("BRASSCRIBE_CATALOGUE_" + name) is { Length: > 0 } v ? v : null;

        /// <summary>Where the screenshots go.</summary>
        public static string Out { get; } = Path.GetFullPath(Env("OUT") ?? "catalogue");

        /// <summary>Screenshots of screens that did not keep still: kept to look at, never compared.</summary>
        public static string UnsteadyOut => Path.Combine(Out, "unsteady");

        /// <summary>This run's name: en, nb, contrast, text200.</summary>
        public static string Run { get; } = Env("RUN") ?? "en";

        /// <summary>What goes before the variant in a screenshot's name ("nb-" in "home--nb-dark").</summary>
        public static string Prefix { get; } = Run == "en" ? "" : Run + "-";

        /// <summary>A contrast theme is on in Windows for this run (the runner script turns it on).</summary>
        public static bool Contrast { get; } = Env("RUN") == "contrast";

        public static Appearance[] Variants { get; } =
            (Env("VARIANTS") ?? "light,dark").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Select(AppearanceSetting.Parse).ToArray();

        /// <summary>The checks run (off at the merge base: only its screenshots are wanted).</summary>
        public static bool Checks { get; } = Env("CHECKS") != "0";

        public static string? Score { get; } = Env("SCORE");

        private static readonly string[]? Only = Env("SCENES")?.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        public static bool Wanted(string scene) => Only is null || Only.Contains(scene);
    }
}
