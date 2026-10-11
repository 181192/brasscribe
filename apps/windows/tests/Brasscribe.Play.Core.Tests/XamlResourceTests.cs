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

    [SkippableFact]
    public void Every_resource_key_the_app_uses_is_defined()
    {
        Skip.If(TestPaths.RepoFile("design/dist/windows/BrasscribeTheme.xaml") is null, TestPaths.Missing("design/dist/windows/BrasscribeTheme.xaml"));
        var defined = Defined();
        var used = new Dictionary<string, string>();
        foreach (var file in Directory.EnumerateFiles(App, "*.xaml", SearchOption.AllDirectories))
        {
            if (file.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}")) continue;
            foreach (Match m in UseRegex().Matches(File.ReadAllText(file))) used.TryAdd(m.Groups[2].Value, Path.GetFileName(file));
        }
        // Code looks keys up by name too (the score view's overlay brushes, the title bar's colours, menu icons):
        // every string that is a key of the design, in the app and in its controls.
        foreach (var (key, file) in CodeKeys(App, Path.Combine(App, "..", "Brasscribe.Play.Controls"))) used.TryAdd(key, file);

        Assert.True(used.Count > 50, $"only {used.Count} keys found; the scan is broken");
        var missing = used.Where(u => !defined.Contains(u.Key) && !WinUi.Contains(u.Key)).Select(u => $"{u.Key} ({u.Value})").Order().ToList();
        Assert.True(missing.Count == 0, "undefined: " + string.Join(", ", missing));
    }

    /// <summary>Bandroom reads the same theme: every design key its XAML and its code use is defined.</summary>
    [SkippableFact]
    public void Every_design_key_Bandroom_uses_is_defined()
    {
        var theme = TestPaths.RepoFile("design/dist/windows/BrasscribeTheme.xaml");
        Skip.If(theme is null, TestPaths.Missing("design/dist/windows/BrasscribeTheme.xaml"));
        string app = Path.Combine(TestPaths.RepoRoot!, "apps", "bandroom", "windows", "src", "Brasscribe.Bandroom");
        var defined = new[] { theme!, Path.Combine(app, "Themes", "Styles.xaml"), Path.Combine(app, "App.xaml") }
            .SelectMany(f => KeyRegex().Matches(File.ReadAllText(f)).Select(m => m.Groups[1].Value)).ToHashSet();
        var used = new Dictionary<string, string>();
        foreach (var file in Directory.EnumerateFiles(app, "*.xaml", SearchOption.AllDirectories).Where(NotBuilt))
            foreach (Match m in UseRegex().Matches(File.ReadAllText(file)))
                if (DesignKeyRegex().IsMatch(m.Groups[2].Value)) used.TryAdd(m.Groups[2].Value, Path.GetFileName(file));
        foreach (var (key, file) in CodeKeys(app)) used.TryAdd(key, file);

        Assert.True(used.Count > 15, $"only {used.Count} keys found; the scan is broken");
        var missing = used.Where(u => !defined.Contains(u.Key)).Select(u => $"{u.Key} ({u.Value})").Order().ToList();
        Assert.True(missing.Count == 0, "undefined: " + string.Join(", ", missing));
    }

    /// <summary>A key of the design that only a brand's own resources have: no key of a neutral role is left under it.</summary>
    [SkippableFact]
    public void The_theme_has_one_key_for_each_role()
    {
        var theme = TestPaths.RepoFile("design/dist/windows/BrasscribeTheme.xaml");
        Skip.If(theme is null, TestPaths.Missing("design/dist/windows/BrasscribeTheme.xaml"));
        var keys = KeyRegex().Matches(File.ReadAllText(theme!)).Select(m => m.Groups[1].Value).ToHashSet();
        Assert.Contains("ScribeTextBrush", keys);
        Assert.Contains("ScribeRadiusMd", keys);
        Assert.Contains("BcCursorBrush", keys);
        foreach (string gone in new[] { "BcTextBrush", "BcBgColor", "BcRadiusMd", "BcSpace4", "BcBodyTextBlockStyle", "BcBrassBrush", "BcStaffBrush", "BcDisplayFontFamily" })
            Assert.DoesNotContain(gone, keys);
    }

    /// <summary>
    /// A colour or brush is looked up in the theme that applies, and in the Pink dictionary while Pink is chosen.
    /// So every themed key the two apps use is in Light, Dark and HighContrast of the theme and of the Pink theme:
    /// a key missing from one of them fails only there, when it runs.
    /// </summary>
    [SkippableFact]
    public void Every_themed_key_the_apps_use_is_in_each_theme_dictionary_and_in_Pink()
    {
        var theme = TestPaths.RepoFile("design/dist/windows/BrasscribeTheme.xaml");
        var pink = TestPaths.RepoFile("design/dist/windows/BrasscribePinkTheme.xaml");
        Skip.If(theme is null || pink is null, TestPaths.Missing("design/dist/windows/BrasscribeTheme.xaml"));
        var dictionaries = new Dictionary<string, HashSet<string>>();
        foreach (var (file, name) in new[] { (theme!, "theme"), (pink!, "Pink") })
            foreach (Match d in ThemeDictionaryRegex().Matches(File.ReadAllText(file)))
                dictionaries[$"{name} {d.Groups[1].Value}"] = KeyRegex().Matches(d.Groups[2].Value).Select(m => m.Groups[1].Value).ToHashSet();
        Assert.Equal(6, dictionaries.Count);
        var themed = dictionaries.Values.SelectMany(k => k).ToHashSet();

        string bandroom = Path.Combine(TestPaths.RepoRoot!, "apps", "bandroom", "windows", "src", "Brasscribe.Bandroom");
        var used = new HashSet<string>();
        foreach (string app in new[] { App, Path.Combine(App, "..", "Brasscribe.Play.Controls"), bandroom })
        {
            foreach (var file in Directory.EnumerateFiles(app, "*.xaml", SearchOption.AllDirectories).Where(NotBuilt))
                foreach (Match m in UseRegex().Matches(File.ReadAllText(file))) used.Add(m.Groups[2].Value);
            foreach (var (key, _) in CodeKeys(app))
            {
                used.Add(key);
                // Code builds a brush from its colour (ThemedResources.Brush, ThemeBrushes.For).
                if (key.EndsWith("Brush", StringComparison.Ordinal)) used.Add(key[..^"Brush".Length] + "Color");
            }
        }
        used.IntersectWith(themed);
        Assert.True(used.Count > 30, $"only {used.Count} themed keys found; the scan is broken");
        var missing = dictionaries.SelectMany(d => used.Where(k => !d.Value.Contains(k)).Select(k => $"{k} ({d.Key})")).Order().ToList();
        Assert.True(missing.Count == 0, "missing: " + string.Join(", ", missing));
    }

    private static bool NotBuilt(string file) =>
        !file.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}") && !file.Contains($"{Path.DirectorySeparatorChar}bin{Path.DirectorySeparatorChar}");

    /// <summary>Every string in the C# of these folders that is a key of the design (Scribe… or Bc…), with its file.</summary>
    private static IEnumerable<(string Key, string File)> CodeKeys(params string[] folders) =>
        folders.SelectMany(folder => Directory.EnumerateFiles(folder, "*.cs", SearchOption.AllDirectories)).Where(NotBuilt)
            .SelectMany(file => CodeKeyRegex().Matches(File.ReadAllText(file)).Select(m => (m.Groups[1].Value, Path.GetFileName(file))));

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

    [GeneratedRegex("\"((?:Scribe|Bc)[A-Z][A-Za-z0-9]+)\"")]
    private static partial Regex CodeKeyRegex();

    [GeneratedRegex("<ResourceDictionary x:Key=\"(Light|Dark|HighContrast)\">(.*?)</ResourceDictionary>", RegexOptions.Singleline)]
    private static partial Regex ThemeDictionaryRegex();

    [GeneratedRegex("^(?:Scribe|Bc)[A-Z]")]
    private static partial Regex DesignKeyRegex();
}
