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
        var variants = Options.VariantsFor(scene);
        store.Set(AppearanceSetting.Key, AppearanceSetting.Serialise(variants[0]));
        store.Set(AppearanceSetting.PinkUnlockedKey, true);
        store.Set(nameof(SettingsViewModel.ReduceMotion), true);
        string work = Path.Combine(Path.GetTempPath(), "brasscribe-catalogue", Guid.NewGuid().ToString("N"));
        long crashes = CrashLogLength();
        var (main, settings) = App.Compose(store, work, forcedTheme: null);
        var window = App.MainWindowInstance!;
        window.HeartbeatEnabled = false;
        window.Activate();
        string shot = ShotName(scene, variants[0]);
        try
        {
            Type? dialog = scene switch
            {
                "export" => typeof(Brasscribe.Play.Dialogs.ExportDialog),
                "settings" => typeof(Brasscribe.Play.Dialogs.SettingsDialog),
                _ => null,
            };
            PreviewScenes.Show(main, scene == "settings" ? "home" : scene, Options.Score);
            await LoadedAsync(window);
            CheckSystem(settings);
            CheckLanguage();

            Picture? first = null;
            foreach (var variant in variants)
            {
                shot = ShotName(scene, variant);
                settings.Appearance = variant;
                Picture? without = null;
                if (dialog is not null)
                {
                    // Opened in each choice, so it shows that choice (a person changes it in the dialog itself). The
                    // screen without it is taken first: the dialog's picture must not be that one.
                    without = (await TakeAsync(window, main, settings, null, null, shot + " (before its dialog)")).Picture;
                    var open = scene == "export" ? window.ShowExportAsync() : window.OpenSettingsAsync();
                    if (open.IsCompleted) throw new ScreenNotTakenException("screen not taken: its dialog was not opened (another one is open, or the screen under it is not the one it opens from)");
                }
                var taken = await TakeAsync(window, main, settings, dialog, without, shot);
                if (Options.Contrast && first is not null)
                {
                    // A contrast theme always wins: every choice must look the same as the first (but in Settings,
                    // whose Appearance box shows the choice).
                    if (scene != "settings" && !taken.Picture!.SameAs(first) && ImageDiff.Of(first, taken.Picture!).Changed > ImageDiff.FloorPixels)
                        Run.Findings.Add(new Finding(ShotName(scene, variants[0]), "contrast-theme",
                            AppearanceSetting.Serialise(variant), "this Appearance choice changed the screen under a contrast theme"));
                }
                else
                {
                    first ??= taken.Picture!;
                    Save(Path.Combine(Options.Out, shot + ".png"), taken.Picture!);
                    Run.Shots.Add(shot);
                    if (Options.Checks) Run.Findings.AddRange(Contrast.Check(shot, taken.Picture!, taken.Texts));
                }
                if (dialog is not null && !await CloseDialogsAsync(window))
                    throw new ScreenNotTakenException("screen not taken: its dialog did not close, so the next one could not open");
            }
        }
        catch (Exception e)
        {
            Run.Failed.Add(e is ScreenNotTakenException ? $"{shot}: {e.Message}" : $"{shot}: {e.GetType().Name}: {e.Message}");
            throw;
        }
        finally
        {
            await CloseDialogsAsync(window);
            // The Pink palette is merged into the app's resources while Pink is chosen: out again before the next
            // screen's window, which has a theme controller of its own.
            // The window takes the theme change in (ActualThemeChanged) before it closes.
            settings.Appearance = Appearance.System;
            await Task.Delay(500);
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
    /// One screenshot of the screen asked for, or <see cref="ScreenNotTakenException"/> after <see cref="SteadyShot.Bound"/>
    /// (its last take is kept in not-taken\ to look at, never compared). Each take waits for two rendered frames,
    /// reads the screen (<see cref="Read"/>) before and after the picture, and counts only when the screen was the
    /// one asked for both times and read the same; <see cref="SteadyShot"/> says the rest: the text is drawn in the
    /// picture, a dialog's picture is not the screen <paramref name="without"/> it, and six such takes in a row are
    /// the same.
    /// </summary>
    /// <param name="dialog">The dialog that must be open on the screen; null when none may be.</param>
    private static async Task<SteadyShot> TakeAsync(MainWindow window, MainViewModel main, SettingsViewModel settings,
        Type? dialog, Picture? without, string shot)
    {
        nint hwnd = WinRT.Interop.WindowNative.GetWindowHandle(window);
        var steady = new SteadyShot(without);
        var clock = Stopwatch.StartNew();
        while (!steady.Done && clock.Elapsed < SteadyShot.Bound)
        {
            await Task.Delay(SteadyShot.Pause);
            if (!await FramesAsync(2)) { steady.NotReady("no frame of it was rendered"); continue; }
            var before = Read(window, hwnd, main, settings, dialog, out string? waiting);
            if (before is null) { steady.NotReady(waiting!); continue; }
            // PrintWindow from a thread of its own, so this one goes on answering.
            var picture = await Task.Run(() => Gdi.CaptureClient(hwnd));
            var after = Read(window, hwnd, main, settings, dialog, out waiting);
            if (after is null) { steady.NotReady(waiting!); continue; }
            steady.Take(picture, before, after);
        }
        File.AppendAllText(Path.Combine(Options.Out, $"takes-{Options.Run}.log"), steady.Summary(shot, clock.Elapsed) + Environment.NewLine);
        if (steady.Done) return steady;
        if (steady.Picture is { } last) Save(Path.Combine(Options.Out, "not-taken", shot + ".png"), last);
        throw steady.NotTaken();
    }

    /// <summary>
    /// Rendered frames from now: the layout and the drawing of what the tree holds at this moment have been done
    /// once the second one starts. False when none came within 2 s.
    /// </summary>
    private static async Task<bool> FramesAsync(int frames)
    {
        var done = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        int left = frames;
        void OnRendering(object? sender, object e)
        {
            if (--left <= 0) done.TrySetResult(true);
        }
        CompositionTarget.Rendering += OnRendering;
        try { return await Task.WhenAny(done.Task, Task.Delay(2000)) == done.Task; }
        finally { CompositionTarget.Rendering -= OnRendering; }
    }

    /// <summary>
    /// The screen as it is now, when it is the one asked for; otherwise null and what it is <paramref name="waiting"/>
    /// for. It is the one asked for when: this screen's window is the app's window, shown and in front; its content
    /// has loaded at the window's size; the frame shows the page of the view model's step; exactly the
    /// <paramref name="dialog"/> asked for is open and has opened (or no dialog at all); the window and the dialog
    /// have the theme of the Appearance choice, with the Pink palette merged or not as the choice says; and every
    /// score on it has its notation drawn.
    /// </summary>
    private static Look? Read(MainWindow window, nint hwnd, MainViewModel main, SettingsViewModel settings, Type? dialog, out string? waiting)
    {
        waiting = Why();
        if (waiting is not null) return null;
        var content = (FrameworkElement)window.Content;
        var (w, h) = Gdi.ClientSize(hwnd);
        string shape = $"{w}x{h} {window.ShownPage?.GetType().Name} {dialog?.Name ?? "no dialog"} {content.ActualTheme}";
        return new Look(shape, Texts(content, w, h));

        string? Why()
        {
            if (!ReferenceEquals(App.MainWindowInstance, window)) return "another window has taken its window's place";
            if (!Gdi.IsShown(hwnd)) return "its window is not shown";
            if (Gdi.GetForegroundWindow() != hwnd)
            {
                window.Activate();
                Gdi.SetForegroundWindow(hwnd);
                return "its window is not in front";
            }
            if (window.Content is not FrameworkElement { IsLoaded: true, XamlRoot: { } xamlRoot } root) return "the window's content has not loaded";
            var (width, height) = Gdi.ClientSize(hwnd);
            double scale = xamlRoot.RasterizationScale;
            if (Math.Abs(xamlRoot.Size.Width * scale - width) > 1.5 || Math.Abs(xamlRoot.Size.Height * scale - height) > 1.5)
                return "the content has not taken the window's size";
            if (window.ShownPage is not FrameworkElement { IsLoaded: true } page || page.GetType() != MainWindow.PageFor(main.Screen))
                return $"the page for {main.Screen} is not shown";

            var open = VisualTreeHelper.GetOpenPopupsForXamlRoot(xamlRoot).Select(p => p.Child).OfType<ContentDialog>().ToList();
            if (dialog is null)
            {
                if (open.Count > 0 || Brasscribe.Play.Services.DialogGate.IsOpen) return "a dialog is still open";
            }
            else if (open.Count != 1 || open[0].GetType() != dialog || !open[0].IsLoaded
                     || !ReferenceEquals(Brasscribe.Play.Services.DialogGate.Opened, open[0]))
                return $"{dialog.Name} has not opened";

            var theme = App.Theme!.Current;
            if (theme != ElementTheme.Default && (root.ActualTheme != theme || open.Any(d => d.ActualTheme != theme)))
                return $"the theme is not {theme} yet";
            bool pink = Application.Current.Resources.MergedDictionaries
                .Any(d => d.Source?.OriginalString.EndsWith("BrasscribePinkTheme.xaml", StringComparison.OrdinalIgnoreCase) == true);
            if (pink != settings.UsesPink) return settings.UsesPink ? "the Pink palette is not merged yet" : "the Pink palette is still merged";
            if (!NotationDrawn(root)) return "the notation is not drawn yet";
            return null;
        }
    }

    /// <summary>Every score view on the screen has an image for each page it shows, and no image shown is still empty.</summary>
    private static bool NotationDrawn(DependencyObject node)
    {
        if (node is UIElement { Visibility: not Visibility.Visible }) return true;
        if (node is Image { Source: null }) return false;
        if (node is Brasscribe.Play.Controls.ScoreView score)
        {
            var shown = score.PagesNear(score.Viewport, margin: 0).ToList();
            return shown.Count > 0 && shown.All(score.HasPageImage);
        }
        for (int i = 0, n = VisualTreeHelper.GetChildrenCount(node); i < n; i++)
            if (!NotationDrawn(VisualTreeHelper.GetChild(node, i))) return false;
        return true;
    }

    /// <summary>
    /// Closes the open dialogs and waits until they have gone (the dialog gate is free again, so the next dialog can
    /// open: one asked for while another is open is not shown). False when one is still there after 10 s.
    /// </summary>
    private static async Task<bool> CloseDialogsAsync(MainWindow window)
    {
        if (window.Content?.XamlRoot is not { } xamlRoot) return true;
        List<ContentDialog> Open() => VisualTreeHelper.GetOpenPopupsForXamlRoot(xamlRoot).Select(p => p.Child).OfType<ContentDialog>().ToList();
        foreach (var d in Open()) d.Hide();
        var clock = Stopwatch.StartNew();
        while (Open().Count > 0 || Brasscribe.Play.Services.DialogGate.IsOpen)
        {
            if (clock.Elapsed > TimeSpan.FromSeconds(10)) return false;
            await Task.Delay(50);
        }
        return true;
    }

    /// <summary>
    /// The run's Windows settings reached the app: the contrast theme, the text size (200 % in its run, 100 % in the
    /// others) and animation effects off (the runner script sets them before it starts the app, which reads them
    /// when it starts). Otherwise nothing in this run shows what its screenshots are named for.
    /// </summary>
    private static void CheckSystem(SettingsViewModel settings)
    {
        if (Options.Contrast && !settings.HighContrast)
            throw new InvalidOperationException("the contrast theme is not on, so nothing in this run shows it");
        var system = new Windows.UI.ViewManagement.UISettings();
        double scale = Options.Run == "text200" ? 2.0 : 1.0;
        if (Math.Abs(system.TextScaleFactor - scale) > 0.001)
            throw new InvalidOperationException($"the text size is {system.TextScaleFactor * 100:0} %, not the {scale * 100:0} % of this run");
        if (system.AnimationsEnabled)
            throw new InvalidOperationException("Windows' animation effects are on: a screen could be taken while it fades or slides in");
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
    private static List<ScreenText> Texts(FrameworkElement root, int width, int height)
    {
        double scale = root.XamlRoot.RasterizationScale;
        var popups = VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).Select(p => p.Child).OfType<FrameworkElement>().ToList();
        var scopes = popups.Any(p => p is ContentDialog) ? popups : popups.Prepend(root).ToList();
        var found = new List<ScreenText>();
        foreach (var scope in scopes) Walk(scope, scale, width, height, found);
        return found.DistinctBy(t => (t.Box, t.Kind)).ToList();
    }

    private static void Walk(DependencyObject node, double scale, int width, int height, List<ScreenText> found)
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
            if (text is not null && BoxOf(element, scale, width, height) is { IsEmpty: false } box) found.Add(text with { Box = box });
            if (element is FontIcon) return;
        }
        for (int i = 0, n = VisualTreeHelper.GetChildrenCount(node); i < n; i++) Walk(VisualTreeHelper.GetChild(node, i), scale, width, height, found);
    }

    /// <summary>Where an element is in the picture, cut to every part above it that scrolls; empty when out of view.</summary>
    private static Box BoxOf(FrameworkElement element, double scale, int width, int height)
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
        return Box.FromDips(r.X, r.Y, r.Width, r.Height, scale).Within(width, height);
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

        /// <summary>This run's name: en, nb, contrast, text200.</summary>
        public static string Run { get; } = Env("RUN") ?? "en";

        /// <summary>What goes before the variant in a screenshot's name ("nb-" in "home--nb-dark").</summary>
        public static string Prefix { get; } = Run == "en" ? "" : Run + "-";

        /// <summary>A contrast theme is on in Windows for this run (the runner script turns it on).</summary>
        public static bool Contrast { get; } = Env("RUN") == "contrast";

        public static Appearance[] Variants { get; } =
            (Env("VARIANTS") ?? "light,dark").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Select(AppearanceSetting.Parse).ToArray();

        /// <summary>Screens taken in Pink (BRASSCRIBE_CATALOGUE_PINK_SCENES); all when not set.</summary>
        private static readonly string[]? PinkScenes = Env("PINK_SCENES")?.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        /// <summary>The choices a screen is taken in: Pink only on the screens for Pink (but under a contrast theme,
        /// where every choice must look the same).</summary>
        public static Appearance[] VariantsFor(string scene) =>
            Contrast || PinkScenes is null || PinkScenes.Contains(scene)
                ? Variants
                : Variants.Where(v => !AppearanceSetting.IsPink(v)).DefaultIfEmpty(Appearance.Light).ToArray();

        /// <summary>The checks run (off at the base: only its screenshots are wanted).</summary>
        public static bool Checks { get; } = Env("CHECKS") != "0";

        public static string? Score { get; } = Env("SCORE");

        private static readonly string[]? Only = Env("SCENES")?.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        public static bool Wanted(string scene) => Only is null || Only.Contains(scene);
    }
}
