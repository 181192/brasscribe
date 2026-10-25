using System.Text.RegularExpressions;
using Brasscribe.Play.Core;
using Brasscribe.Play.Core.Engine;
using Xunit;

namespace Brasscribe.Play.Core.Tests;

public class ProductTests
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
    public void The_apps_target_is_the_number_the_core_gives_the_band()
    {
        Assert.Equal(Defined("SC_TARGET_BRASS"), Product.CoreTarget);
        Assert.NotEqual(Defined("SC_TARGET_FRETTED"), Product.CoreTarget);
        Assert.Equal("brass", Product.Target);
    }

    [Theory]
    [InlineData("brass", true)]
    [InlineData("fretted", false)]
    [InlineData("choir", false)] // a target this app does not know
    [InlineData(null, false)]
    public void A_job_is_the_apps_when_its_target_is(string? target, bool ours) =>
        Assert.Equal(ours, new Job("j", "solo", JobStatus.Succeeded, 1, [], Target: target).IsOurs);
}
