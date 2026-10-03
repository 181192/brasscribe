using System.Text.RegularExpressions;

namespace Brasscribe.Bandroom.Core.Supervisor;

/// <summary>
/// pixi refused the engine workspace because it is older than <c>requires-pixi</c> in pixi.toml asks for: "this project
/// requires pixi '>=0.80', but you have pixi 0.79.0". Starting again can't fix that; only a Bandroom that bundles a
/// newer pixi can.
/// </summary>
/// <param name="Required">What the workspace asks for, as pixi wrote it (">=0.80").</param>
/// <param name="Found">The version of the pixi that refused ("0.79.0").</param>
/// <param name="Message">pixi's own line as it wrote it, for the tech person.</param>
public sealed partial record PixiRefusal(string Required, string Found, string Message)
{
    /// <summary>
    /// The refusal in one line of pixi's output, or null. Matches the words only: the "Error: ×" before them depends on
    /// the console's code page.
    /// </summary>
    public static PixiRefusal? Parse(string line)
    {
        var m = Pattern().Match(line);
        return m.Success ? new PixiRefusal(m.Groups[1].Value, m.Groups[2].Value, line.Trim()) : null;
    }

    /// <summary>The first refusal in these lines, or null.</summary>
    public static PixiRefusal? Find(IEnumerable<string> lines) =>
        lines.Select(Parse).FirstOrDefault(r => r is not null);

    [GeneratedRegex(@"requires pixi '([^']+)', but you have pixi ([0-9][0-9A-Za-z.+-]*)")]
    private static partial Regex Pattern();
}
