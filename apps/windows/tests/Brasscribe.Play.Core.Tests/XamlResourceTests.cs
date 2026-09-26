using System.Text.RegularExpressions;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// A missing XAML resource key only fails when the page loads on Windows. This checks, off Windows,
/// that every {StaticResource}/{ThemeResource} key the app's XAML (and the score view's code) uses is
/// defined by the linked design theme (design/dist/windows/BrasscribeTheme.xaml), by Themes/Styles.xaml
/// or App.xaml, or is a WinUI resource the app relies on.
/// </summary>
public partial class XamlResourceTests
{
    /// <summary>WinUI's own resources the app uses.</summary>
    private static readonly HashSet<string> WinUi =
    [
        "AccentButtonStyle", "DefaultButtonStyle", "DefaultToggleButtonStyle", "SymbolThemeFontFamily",
        "TitleLargeTextBlockStyle", "TitleTextBlockStyle", "SubtitleTextBlockStyle", "BodyLargeTextBlockStyle",
        "BodyTextBlockStyle", "BodyStrongTextBlockStyle", "CaptionTextBlockStyle",
        "SystemColorWindowColor", "SystemColorWindowTextColor", "SystemColorHighlightColor", "SystemColorHighlightTextColor",
        "SystemColorButtonFaceColor", "SystemColorButtonTextColor", "SystemColorHotlightColor",
    ];

    private static string App => Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play");

    private static HashSet<string> Defined()
    {
        var files = new List<string> { Path.Combine(App, "Themes", "Styles.xaml"), Path.Combine(App, "App.xaml") };
        if (TestPaths.RepoFile("design/dist/windows/BrasscribeTheme.xaml") is { } theme) files.Add(theme);
        return files.SelectMany(f => KeyRegex().Matches(File.ReadAllText(f)).Select(m => m.Groups[1].Value)).ToHashSet();
    }

    [Fact]
    public void Every_resource_key_the_app_uses_is_defined()
    {
        if (TestPaths.RepoFile("design/dist/windows/BrasscribeTheme.xaml") is null) return;
        var defined = Defined();
        var used = new Dictionary<string, string>();
        foreach (var file in Directory.EnumerateFiles(App, "*.xaml", SearchOption.AllDirectories))
        {
            if (file.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}")) continue;
            foreach (Match m in UseRegex().Matches(File.ReadAllText(file))) used.TryAdd(m.Groups[2].Value, Path.GetFileName(file));
        }
        // The score view draws its overlays with these brushes from code.
        var control = Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play.Controls", "ScoreView.cs");
        foreach (Match m in CodeBrushRegex().Matches(File.ReadAllText(control))) used.TryAdd(m.Groups[1].Value, "ScoreView.cs");
        foreach (Match m in AppResourceRegex().Matches(string.Concat(Directory.EnumerateFiles(App, "*.cs", SearchOption.AllDirectories)
                     .Where(f => !f.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}")).Select(File.ReadAllText))))
            used.TryAdd(m.Groups[1].Value, "code");

        Assert.True(used.Count > 50, $"only {used.Count} keys found; the scan is broken");
        var missing = used.Where(u => !defined.Contains(u.Key) && !WinUi.Contains(u.Key)).Select(u => $"{u.Key} ({u.Value})").Order().ToList();
        Assert.True(missing.Count == 0, "undefined: " + string.Join(", ", missing));
    }

    [Fact]
    public void The_theme_is_linked_from_design_not_copied()
    {
        var csproj = File.ReadAllText(Path.Combine(App, "Brasscribe.Play.csproj"));
        Assert.Contains(@"dist\windows\BrasscribeTheme.xaml", csproj);
        Assert.Contains(@"dist\icons\windows\Assets\*", csproj);
        Assert.False(File.Exists(Path.Combine(App, "Themes", "BrasscribeTheme.xaml")));
        Assert.False(File.Exists(Path.Combine(App, "Themes", "Tokens.xaml")));
    }

    [GeneratedRegex("x:Key=\"([A-Za-z0-9]+)\"")]
    private static partial Regex KeyRegex();

    [GeneratedRegex(@"\{(StaticResource|ThemeResource) ([A-Za-z0-9]+)\}|ResourceKey=""(?<2>[A-Za-z0-9]+)""")]
    private static partial Regex UseRegex();

    [GeneratedRegex("Brush\\(\"(Bc[A-Za-z]+)\"\\)")]
    private static partial Regex CodeBrushRegex();

    [GeneratedRegex("Resources\\[\"(Bc[A-Za-z]+)\"\\]")]
    private static partial Regex AppResourceRegex();
}
