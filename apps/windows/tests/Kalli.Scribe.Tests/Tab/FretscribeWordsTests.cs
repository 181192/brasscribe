using System.Text.RegularExpressions;
using System.Xml.Linq;
using Kalli.Scribe.Capture;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;
using Kalli.Scribe.Tab;
using Kalli.Scribe.ViewModels;

namespace Kalli.Scribe.Tests;

/// <summary>
/// Fretscribe's .resw files from the source tree: both languages have the same keys and placeholders, every x:Uid in
/// its XAML has resources and none is orphaned, its switches say On and Off in the app's language, every key the code
/// it runs asks for exists, and its words name no other product.
/// </summary>
public partial class FretscribeWordsTests
{
    private static string Windows => Path.Combine(TestPaths.RepoRoot!, "apps", "windows");
    private static string App => Path.Combine(Windows, "products", "fretscribe", "Kalli.Fretscribe");

    private static Dictionary<string, string> Load(string lang) =>
        ReswStrings.Parse(XDocument.Load(Path.Combine(App, "Strings", lang, "Resources.resw")));

    private static IEnumerable<string> Xaml() => Directory.EnumerateFiles(App, "*.xaml", SearchOption.AllDirectories)
        .Where(f => !f.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}"));

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
        var uids = Xaml().SelectMany(f => UidRegex().Matches(File.ReadAllText(f)).Select(m => m.Groups[1].Value)).ToHashSet();
        Assert.NotEmpty(uids);
        foreach (var uid in uids)
            Assert.True(keys.Any(k => k.StartsWith(uid + ".", StringComparison.Ordinal)), $"x:Uid {uid} has no resources");
        var uidKeys = keys.Where(k => k.Contains('.')).Select(k => k[..k.IndexOf('.')]).ToHashSet();
        Assert.Empty(uidKeys.Except(uids));
    }

    [Fact]
    public void Every_toggle_switch_says_on_and_off_in_the_apps_language()
    {
        var en = Load("en-US");
        var nb = Load("nb-NO");
        XNamespace x = "http://schemas.microsoft.com/winfx/2006/xaml";
        var switches = Xaml().SelectMany(f => XDocument.Load(f).Descendants().Where(e => e.Name.LocalName == "ToggleSwitch")).ToList();
        Assert.NotEmpty(switches);
        foreach (var s in switches)
        {
            string uid = (string?)s.Attribute(x + "Uid") ?? throw new Xunit.Sdk.XunitException($"a ToggleSwitch without x:Uid: {s}");
            Assert.Equal(("On", "Off"), (en[$"{uid}.OnContent"], en[$"{uid}.OffContent"]));
            Assert.Equal(("På", "Av"), (nb[$"{uid}.OnContent"], nb[$"{uid}.OffContent"]));
        }
    }

    /// <summary>The shared code this app runs, and its own: their string keys, and the ones built from enum names.</summary>
    [Fact]
    public void Every_string_key_the_code_uses_exists()
    {
        var keys = Load("en-US").Keys.ToHashSet();
        string[] shared =
        [
            "features/Kalli.Scribe.Play/ViewModels/StartViewModel.cs", "features/Kalli.Scribe.Play/ViewModels/TranscriptionViewModel.cs",
            "features/Kalli.Scribe.Play/ViewModels/SettingsViewModel.cs", "features/Kalli.Scribe.Play/ViewModels/ErrorViewModel.cs",
            "features/Kalli.Scribe.Play/ViewModels/LibraryViewModel.cs", "services/Kalli.Scribe.Services/Engine/ConnectionMonitor.cs",
            "services/Kalli.Scribe.Services/Services/ScoreTitles.cs",
        ];
        var files = shared.Select(f => Path.Combine(Windows, f))
            .Concat(Directory.EnumerateFiles(Path.Combine(Windows, "features", "Kalli.Scribe.Tab"), "*.cs", SearchOption.AllDirectories))
            .Concat(Directory.EnumerateFiles(App, "*.cs", SearchOption.AllDirectories))
            .Where(f => !f.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}"));
        var used = new HashSet<string>();
        foreach (var file in files)
            foreach (Match m in CodeKeyRegex().Matches(File.ReadAllText(file)))
                if (m.Groups[1].Value != "Pink_Unlocked") used.Add(m.Groups[1].Value); // Pink is Brasscribe's, unlocked from its own Settings

        foreach (var k in Enum.GetNames<TabScreen>()) used.Add($"Screen_{k}");
        foreach (var k in Enum.GetValues<RecordingState>().Where(s => s != RecordingState.Here)) used.Add($"Tab_Practice_{k}");
        foreach (var k in Enum.GetNames<FrettingHand>()) used.Add($"Tab_Hand_{k}");
        foreach (var k in Enum.GetNames<Reads>()) used.Add($"Tab_Reads_{k}");
        foreach (var i in Instruments.All)
        {
            used.Add($"Tab_Instrument_{i}");
            used.Add($"Tab_TooOld_{i}");
            used.Add($"Tab_What_Song_Desc_{i}");
            used.Add($"Tab_KindWithStrings_{i}");
            foreach (var kind in i.Kinds().Where(k => YourInstrument.StringsOf(k) is null)) used.Add($"Tab_Kind_{kind}");
        }
        foreach (var k in Enum.GetNames<ErrorKind>()) { used.Add($"Error_{k}_Title"); used.Add($"Error_{k}_Reason"); used.Add($"Error_{k}_Step1"); }
        foreach (var k in Enum.GetNames<InputBand>()) used.Add($"Start_Level_{k}");
        foreach (var k in Enum.GetNames<CaptureNoticeKind>()) used.Add($"Start_Notice_{k}");
        foreach (var k in TranscriptionViewModel.StepKeys(TabProfiles.Tab)) used.Add($"Transcribe_Step_{k}");
        // What the computer answers for a tab job, in the app's words.
        foreach (var k in new[] { "Error_Unreachable", "Error_Engine", "Error_NeedsPairing", "Error_NotFound", "Error_Options", "Error_Timeout", "Error_TooLarge" })
            used.Add(k);

        Assert.True(used.Count > 100, $"only {used.Count} keys found; the scan is broken");
        var missing = used.Where(k => !keys.Contains(k)).Order().ToList();
        Assert.True(missing.Count == 0, "missing: " + string.Join(", ", missing));
    }

    [Fact]
    public void Every_tuning_an_instrument_has_has_a_name()
    {
        IStrings s = new ReswStrings(Load("nb-NO"));
        foreach (var kind in Instruments.All.SelectMany(i => i.Kinds()))
            foreach (var tuning in kind.Tunings())
                Assert.NotEqual(tuning, YourInstrumentViewModel.TuningName(tuning, s));
    }

    [Fact]
    public void The_words_name_no_other_product()
    {
        foreach (var lang in new[] { "en-US", "nb-NO" })
            foreach (var (key, value) in Load(lang))
            {
                Assert.False(Regex.IsMatch(value, @"\bBrasscribe\b|\bscores?\b|\bpartitur", RegexOptions.IgnoreCase), $"{lang} {key}: {value}");
            }
    }

    private static List<int> Placeholders(string s) =>
        PlaceholderRegex().Matches(s).Select(m => int.Parse(m.Groups[1].Value, System.Globalization.CultureInfo.InvariantCulture)).Distinct().Order().ToList();

    [GeneratedRegex("x:Uid=\"([A-Za-z0-9]+)\"")]
    private static partial Regex UidRegex();

    [GeneratedRegex("\"((?:Duration|Screen|Start|Transcribe|Connection|CancelDialog|Settings|Library|Error|Back|Tab|Song|SongOptions|Notice|Score|Pink)(?:_[A-Za-z0-9]+)+|AppWindowTitle)\"")]
    private static partial Regex CodeKeyRegex();

    [GeneratedRegex(@"\{(\d+)[^}]*\}")]
    private static partial Regex PlaceholderRegex();
}
