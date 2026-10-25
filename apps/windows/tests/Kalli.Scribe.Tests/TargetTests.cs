using System.Text.RegularExpressions;
using Kalli.Scribe;
using Kalli.Scribe.Engine;
using Xunit;

namespace Kalli.Scribe.Tests;

public class TargetTests
{
    /// <summary>The value of a <c>#define</c> in the core's C header.</summary>
    private static int Defined(string name)
    {
        var header = File.ReadAllText(TestPaths.RepoFile("core/bindings/c/scribe.h")!);
        var m = Regex.Match(header, $@"^#define {name} (\d+)\s*$", RegexOptions.Multiline);
        Assert.True(m.Success, $"{name} is not defined in core/bindings/c/scribe.h");
        return int.Parse(m.Groups[1].Value);
    }

    [Fact]
    public void Each_target_is_the_number_the_core_gives_it()
    {
        Assert.Equal(Defined("SC_TARGET_BRASS"), Target.Brass.CoreId);
        Assert.Equal(Defined("SC_TARGET_FRETTED"), Target.Fretted.CoreId);
        Assert.Equal(("brass", "fretted"), (Target.Brass.Id, Target.Fretted.Id));
    }

    [Theory]
    [InlineData("brass", true)]
    [InlineData("fretted", false)]
    [InlineData("choir", false)] // a target this app does not know
    [InlineData(null, false)]
    public void A_job_is_the_targets_when_the_engine_says_so(string? target, bool ours) =>
        Assert.Equal(ours, Target.Brass.Makes(new Job("j", "solo", JobStatus.Succeeded, 1, [], Target: target).Target));

    /// <summary>
    /// The shared projects (services, features) name no product in what they say or store: each product hands in its
    /// own names. The engine's name for itself on the network ("Brasscribe on …", <c>Wire.ServerNamePrefix</c>) and the
    /// repository's address are the exceptions, until they take neutral ones.
    /// </summary>
    [Fact]
    public void Shared_code_names_no_product()
    {
        var windows = Path.Combine(TestPaths.RepoRoot!, "apps", "windows");
        var literal = new Regex("\"[^\"\n]*\\b(Brasscribe|Fretscribe)\\b[^\"\n]*\"", RegexOptions.IgnoreCase);
        // Brasscribe's hidden palette is the product's: shared code knows only that an app may have one.
        var pink = new Regex("pink", RegexOptions.IgnoreCase);
        var found = new List<string>();
        foreach (var level in new[] { "services", "features" })
            foreach (var file in Directory.EnumerateFiles(Path.Combine(windows, level), "*.cs", SearchOption.AllDirectories))
            {
                if (file.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}")) continue;
                foreach (var (text, n) in File.ReadLines(file).Select((l, i) => (l, i + 1)))
                {
                    string line = text.Replace("github.com/181192/brasscribe", "");
                    if (!line.TrimStart().StartsWith("//") && ((literal.IsMatch(line) && !line.Contains("const string ServerNamePrefix = ")) || pink.IsMatch(line)))
                        found.Add($"{Path.GetRelativePath(windows, file)}:{n}");
                }
            }
        Assert.True(found.Count == 0, "product names in shared code: " + string.Join(", ", found));
    }
}
