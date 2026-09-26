using System.Text.RegularExpressions;
using System.Xml.Linq;
using Brasscribe.Play.Core.Capture;
using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;

namespace Brasscribe.Play.Core.Tests;

/// <summary>
/// Checks the WinUI app's .resw files from the source tree: both languages have the same keys and
/// placeholders, every x:Uid in the XAML has resources and none is orphaned, and every string key
/// the code asks for exists. This catches the usual WinUI localisation mistakes without Windows.
/// </summary>
public partial class LocalizationTests
{
    private static string App => Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play");
    private static string CoreSrc => Path.Combine(TestPaths.RepoRoot!, "apps", "windows", "src", "Brasscribe.Play.Core");

    private static Dictionary<string, string> Load(string lang) =>
        ReswStrings.Parse(XDocument.Load(Path.Combine(App, "Strings", lang, "Resources.resw")));

    [Fact]
    public void Both_languages_have_the_same_keys_and_placeholders()
    {
        var en = Load("en-US");
        var nb = Load("nb-NO");
        Assert.Empty(en.Keys.Except(nb.Keys));
        Assert.Empty(nb.Keys.Except(en.Keys));
        foreach (var (key, value) in en)
        {
            Assert.False(string.IsNullOrWhiteSpace(value), $"{key} is empty in en-US");
            Assert.False(string.IsNullOrWhiteSpace(nb[key]), $"{key} is empty in nb-NO");
            Assert.Equal(Placeholders(value), Placeholders(nb[key]));
        }
    }

    [Fact]
    public void Every_xuid_has_resources_and_no_resource_is_orphaned()
    {
        var keys = Load("en-US").Keys.ToList();
        var uids = Directory.EnumerateFiles(App, "*.xaml", SearchOption.AllDirectories)
            .Where(f => !f.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}"))
            .SelectMany(f => UidRegex().Matches(File.ReadAllText(f)).Select(m => m.Groups[1].Value))
            .ToHashSet();
        Assert.NotEmpty(uids);
        foreach (var uid in uids)
            Assert.True(keys.Any(k => k.StartsWith(uid + ".", StringComparison.Ordinal)), $"x:Uid {uid} has no resources");

        var uidKeys = keys.Where(k => k.Contains('.')).Select(k => k[..k.IndexOf('.')]).ToHashSet();
        Assert.Empty(uidKeys.Except(uids));
    }

    [Fact]
    public void Every_string_key_the_code_uses_exists()
    {
        var keys = Load("en-US").Keys.ToHashSet();
        var used = new HashSet<string>();
        foreach (var file in Directory.EnumerateFiles(CoreSrc, "*.cs", SearchOption.AllDirectories)
                     .Concat(Directory.EnumerateFiles(App, "*.cs", SearchOption.AllDirectories)))
        {
            if (file.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}")) continue;
            foreach (Match m in CodeKeyRegex().Matches(File.ReadAllText(file))) used.Add(m.Groups[1].Value);
        }

        // Keys built at run time from enum names.
        foreach (var k in Enum.GetNames<Screen>()) used.Add($"Screen_{k}");
        foreach (var k in Enum.GetNames<SourceKind>()) { used.Add($"Kind_{k}_Label"); used.Add($"Kind_{k}_Description"); }
        foreach (var k in Enum.GetNames<InputBand>()) used.Add($"Start_Level_{k}");
        foreach (var k in Enum.GetNames<CaptureNoticeKind>()) used.Add($"Start_Notice_{k}");
        foreach (var k in Enum.GetNames<ExportFormat>()) used.Add($"Export_Format_{k}");
        foreach (var k in OutputOptionsViewModel.Keys) used.Add(k is null ? "Key_AsRecorded" : $"Key_{k}");
        foreach (var k in Enum.GetNames<ErrorKind>()) { used.Add($"Error_{k}_Title"); used.Add($"Error_{k}_Reason"); used.Add($"Error_{k}_Step1"); }
        foreach (var k in new[] { "Pdf", "MusicXml", "Audio", "Midi", "TalkingScore", "Braille" }) { used.Add($"Export_{k}"); used.Add($"Export_{k}_For"); }
        foreach (var profile in SourceKindViewModel.Profiles.Values)
            foreach (var k in TranscriptionViewModel.StepKeys(profile)) used.Add($"Transcribe_Step_{k}");

        Assert.True(used.Count > 100, $"only {used.Count} keys found; the scan is broken");
        var missing = used.Where(k => !keys.Contains(k)).Order().ToList();
        Assert.True(missing.Count == 0, "missing: " + string.Join(", ", missing));
    }

    [Fact]
    public void Resw_strings_format_with_the_current_culture()
    {
        IStrings s = new ReswStrings(Load("nb-NO"));
        Assert.Equal("Takt 12 av 128", s.Format("Player_Position", 12, 128));
        Assert.Equal("Missing_Key", s["Missing_Key"]);
    }

    private static List<int> Placeholders(string s) =>
        PlaceholderRegex().Matches(s).Select(m => int.Parse(m.Groups[1].Value, System.Globalization.CultureInfo.InvariantCulture)).Distinct().Order().ToList();

    [GeneratedRegex("x:Uid=\"([A-Za-z0-9]+)\"")]
    private static partial Regex UidRegex();

    // Resource keys in code: "Prefix_Name" string literals with a known prefix.
    [GeneratedRegex("\"((?:Duration|Screen|Start|Kind|Transcribe|CancelDialog|Score|Player|Mixer|Export|Output|Settings|Key|Shortcuts?|Review|Library|Error|Back|Title|FinishLater)(?:_[A-Za-z]+)+|AppWindowTitle)\"")]
    private static partial Regex CodeKeyRegex();

    [GeneratedRegex(@"\{(\d+)[^}]*\}")]
    private static partial Regex PlaceholderRegex();
}
