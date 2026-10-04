using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Text.Json;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;
using Brasscribe.ScreenCheck;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Microsoft.VisualStudio.TestTools.UnitTesting.AppContainer;

namespace Brasscribe.Play.Catalogue;

/// <summary>
/// Every screen of the app with sample content (the scenes of <see cref="PreviewScenes"/>, Settings and Share or
/// print), each in the Appearance choices this run asks for, switched while the screen is open, as a person does
/// in Settings. For each: a screenshot (RenderTargetBitmap, with open dialogs drawn on top), the contrast of every
/// text and icon measured on it, text cut off, and, from a separate process (tools/ScreenCheck), the Axe.Windows
/// rules and a walk with Tab. One process per language, contrast theme and text size: the runner script sets
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
        var (main, settings) = App.Compose(store, work, forcedTheme: null);
        var window = App.MainWindowInstance!;
        window.HeartbeatEnabled = false;
        window.Activate();
        try
        {
            PreviewScenes.Show(main, scene == "settings" ? "home" : scene, Options.Score);
            var root = await LoadedAsync(window);
            if (scene is "export" or "settings")
            {
                await SteadyAsync(root);
                _ = scene == "export" ? window.ShowExportAsync() : window.OpenSettingsAsync();
            }
            if (Options.Contrast && !settings.HighContrast)
                throw new InvalidOperationException("the contrast theme is not on, so nothing in this run shows it");

            Picture? first = null;
            foreach (var variant in Options.Variants)
            {
                settings.Appearance = variant;
                var (picture, steady) = await SteadyAsync(root);
                if (Options.Contrast && first is not null)
                {
                    // A contrast theme always wins: every choice must look the same as the first.
                    if (!picture.SameAs(first) && ImageDiff.Of(first, picture).Changed > ImageDiff.FloorPixels)
                        Run.Findings.Add(new Finding(ShotName(scene, Options.Variants[0]), "contrast-theme",
                            AppearanceSetting.Serialise(variant), "this Appearance choice changed the screen under a contrast theme"));
                    continue;
                }
                first ??= picture;
                string shot = ShotName(scene, variant);
                Save(Path.Combine(steady ? Options.Out : Options.UnsteadyOut, shot + ".png"), picture);
                Run.Shots.Add(shot);
                if (!steady) Run.Unsteady.Add(shot);
                if (Options.Checks) Run.Findings.AddRange(Contrast.Check(shot, picture, Texts(root, picture)));
                if (Options.Checks && Options.Scanner is { } scanner && variant == Options.Variants[0])
                    Run.Findings.AddRange(await ScanAsync(scanner, window, shot));
            }
        }
        catch (Exception e)
        {
            Run.Failed.Add($"{scene}: {e.GetType().Name}: {e.Message}");
            throw;
        }
        finally
        {
            CloseDialogs(window);
            window.Close();
            Save();
        }
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

    /// <summary>The window's content, with every open popup (a dialog, a flyout) drawn over it where it is.</summary>
    private static async Task<Picture> CaptureAsync(FrameworkElement root)
    {
        var picture = await RenderAsync(root);
        foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot))
        {
            if (popup.Child is not FrameworkElement child || child.ActualWidth < 1 || child.ActualHeight < 1) continue;
            var at = child.TransformToVisual(null).TransformPoint(new Windows.Foundation.Point(0, 0));
            double scale = root.XamlRoot.RasterizationScale;
            picture.Compose(await RenderAsync(child), (int)Math.Round(at.X * scale), (int)Math.Round(at.Y * scale));
        }
        return picture;
    }

    private static async Task<Picture> RenderAsync(UIElement element)
    {
        var bitmap = new RenderTargetBitmap();
        await bitmap.RenderAsync(element);
        var pixels = (await bitmap.GetPixelsAsync()).ToArray();
        return new Picture(bitmap.PixelWidth, bitmap.PixelHeight, pixels);
    }

    private static void CloseDialogs(MainWindow window)
    {
        if (window.Content?.XamlRoot is not { } xamlRoot) return;
        foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(xamlRoot))
            if (popup.Child is ContentDialog dialog) dialog.Hide();
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

    // ---- Axe.Windows and the keyboard, from another process ----

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(nint hwnd);

    /// <summary>
    /// tools/ScreenCheck scans this window from its own process while this one waits without blocking its UI thread
    /// (UI Automation calls into this process are answered on that thread).
    /// </summary>
    private static async Task<List<Finding>> ScanAsync(string scanner, MainWindow window, string shot)
    {
        nint hwnd = WinRT.Interop.WindowNative.GetWindowHandle(window);
        window.Activate();
        SetForegroundWindow(hwnd);
        string result = Path.Combine(Options.Out, "scans", shot + ".json");
        Directory.CreateDirectory(Path.GetDirectoryName(result)!);
        var psi = new ProcessStartInfo(scanner) { UseShellExecute = false };
        foreach (var a in new[] { "scan", "--pid", Environment.ProcessId.ToString(), "--hwnd", hwnd.ToString(), "--shot", shot, "--out", result })
            psi.ArgumentList.Add(a);
        using var process = Process.Start(psi) ?? throw new InvalidOperationException("tools/ScreenCheck did not start");
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(2));
        await process.WaitForExitAsync(timeout.Token);
        if (process.ExitCode != 0 || !File.Exists(result))
            throw new InvalidOperationException($"tools/ScreenCheck scan of {shot} failed (exit {process.ExitCode})");
        return JsonSerializer.Deserialize<List<Finding>>(File.ReadAllText(result), new JsonSerializerOptions(JsonSerializerDefaults.Web)) ?? [];
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

        /// <summary>tools/ScreenCheck's exe, for Axe.Windows and the Tab walk; without it they are not run.</summary>
        public static string? Scanner { get; } = Env("SCANNER");

        public static string? Score { get; } = Env("SCORE");

        private static readonly string[]? Only = Env("SCENES")?.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        public static bool Wanted(string scene) => Only is null || Only.Contains(scene);
    }
}
