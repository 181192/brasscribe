using System.Text.Json;
using Brasscribe.ScreenCheck;

// ScreenCheck <command> [--name value]...
//
//   scan     --pid P --hwnd H --shot NAME --out FILE   Axe.Windows and a walk with Tab on a window; findings to FILE (JSON)
//   bandroom --exe EXE --out DIR --run en|nb|contrast|text200 [--themes light,dark] [--scenes a,b:state] [--checks 0]
//                                                       Bandroom's catalogue: one start per view, its screenshots and checks
//   system   --contrast on|off | --text-scale PERCENT|off   a contrast theme or a text size for the next run (this user)
//   verdict  --dir DIR --known FILE --title TEXT [--summary FILE]
//                                                       the findings of a catalogue's runs: exit 0 none new, 2 new, 3 screens not taken
//   compare  --before DIR --after DIR --report DIR      screenshots at the merge base against these: exit 0 same, 1 changed
//
// Exit 3 when a command could not do its work (nothing was checked); 2 for wrong usage.
var options = Options.Parse(args.Skip(1));
try
{
    return args.FirstOrDefault() switch
    {
        "scan" => Scan.Run(int.Parse(options.Need("pid")), nint.Parse(options.Need("hwnd")), options.Need("shot"), options.Need("out")),
        "bandroom" => BandroomCatalogue.Run(options),
        "system" => SystemState.Run(options),
        "verdict" => Verdict(options),
        "compare" => Compare(options),
        _ => Usage(),
    };
}
catch (UsageException e)
{
    Console.Error.WriteLine(e.Message);
    return Usage();
}
catch (Exception e)
{
    Console.Error.WriteLine(e);
    return 3;
}

static int Usage()
{
    Console.Error.WriteLine("usage: ScreenCheck scan|bandroom|system|verdict|compare [--name value]... (see Program.cs)");
    return 2;
}

static int Verdict(Options o)
{
    string dir = o.Need("dir");
    var runs = Directory.Exists(dir) ? Directory.GetFiles(dir, "catalogue-*.json").Order().Select(CatalogueRun.Load).ToList() : [];
    var verdict = Brasscribe.ScreenCheck.Verdict.Of(runs, CatalogueRun.LoadKnown(o.Need("known")));
    string md = verdict.Markdown(o.Need("title"));
    Console.WriteLine(md);
    if (o.Get("summary") is { } summary) File.AppendAllText(summary, md);
    return verdict.ExitCode;
}

static int Compare(Options o)
{
    string before = o.Need("before"), after = o.Need("after"), report = o.Need("report");
    // Screens that did not keep still on either side are not compared.
    var skip = new[] { before, after }.Where(Directory.Exists)
        .SelectMany(d => Directory.GetFiles(d, "catalogue-*.json")).SelectMany(f => CatalogueRun.Load(f).Unsteady).ToHashSet();
    if (Directory.Exists(report)) Directory.Delete(report, true);
    Directory.CreateDirectory(report);
    var result = ScreenshotReport.Write(before, after, report, Png.Load, Png.Save, skip);
    Console.WriteLine(result.Summary);
    return result.Any ? 1 : 0;
}

internal sealed class UsageException(string message) : Exception(message);

/// <summary>"--name value" pairs.</summary>
internal sealed class Options
{
    private readonly Dictionary<string, string> _values = [];

    public static Options Parse(IEnumerable<string> args)
    {
        var o = new Options();
        string? name = null;
        foreach (var a in args)
        {
            if (a.StartsWith("--", StringComparison.Ordinal)) name = a[2..];
            else if (name is not null) { o._values[name] = a; name = null; }
            else throw new UsageException($"unexpected argument {a}");
        }
        if (name is not null) throw new UsageException($"--{name} needs a value");
        return o;
    }

    public string? Get(string name) => _values.TryGetValue(name, out var v) ? v : null;

    public string Need(string name) => Get(name) ?? throw new UsageException($"--{name} is needed");

    public string[] List(string name, string fallback) =>
        (Get(name) ?? fallback).Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
}

internal static class JsonFiles
{
    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web) { WriteIndented = true };
}
