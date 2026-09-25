using System.Diagnostics;
using Axe.Windows.Automation;
using Axe.Windows.Automation.Data;

// Usage: AxeScan <path to BrasscribePlay.exe> <output dir> [file to open]...
// Each run starts the app (optionally opening a file, which takes it to the score screen), waits
// for its window, scans it with Axe.Windows and writes an .a11ytest file per window. Exit code 1
// when any rule fails, so CI can gate on it.
if (args.Length < 2)
{
    Console.Error.WriteLine("usage: AxeScan <exe> <output dir> [file to open]...");
    return 2;
}

string exe = Path.GetFullPath(args[0]);
string outDir = Path.GetFullPath(args[1]);
Directory.CreateDirectory(outDir);
var runs = args.Length > 2 ? args.Skip(2).Select(a => (string?)Path.GetFullPath(a)).Prepend(null).ToList() : [null];

int failures = 0;
foreach (var file in runs)
{
    string label = file is null ? "start" : Path.GetFileNameWithoutExtension(file);
    var psi = new ProcessStartInfo(exe) { UseShellExecute = false, WorkingDirectory = Path.GetDirectoryName(exe)! };
    if (file is not null) psi.ArgumentList.Add(file);
    using var app = Process.Start(psi) ?? throw new InvalidOperationException("could not start " + exe);
    try
    {
        var deadline = DateTime.UtcNow.AddSeconds(90);
        while (app.MainWindowHandle == 0 && DateTime.UtcNow < deadline && !app.HasExited)
        {
            Thread.Sleep(500);
            app.Refresh();
        }
        if (app.HasExited) throw new InvalidOperationException($"the app exited with code {app.ExitCode} before showing a window");
        if (app.MainWindowHandle == 0) throw new TimeoutException("no main window after 90 s");
        Thread.Sleep(file is null ? 3000 : 8000); // let the screen (and the score render) settle

        var config = Config.Builder.ForProcessId(app.Id)
            .WithOutputDirectory(outDir)
            .WithOutputFileFormat(OutputFileFormat.A11yTest)
            .WithAlwaysSaveTestFile()
            .Build();
        var output = ScannerFactory.CreateScanner(config).Scan(new ScanOptions(scanId: label));
        foreach (var window in output.WindowScanOutputs)
        {
            Console.WriteLine($"[{label}] {window.ErrorCount} errors; results in {window.OutputFile.A11yTest}");
            foreach (var e in window.Errors)
            {
                var props = e.Element.Properties;
                string name = props is not null && props.TryGetValue("Name", out var n) ? n : "";
                string type = props is not null && props.TryGetValue("ControlType", out var t) ? t : "";
                Console.WriteLine($"  {e.Rule.ID}: {e.Rule.Description} | {type} \"{name}\"");
            }
            failures += window.ErrorCount;
        }
    }
    finally
    {
        if (!app.HasExited) app.Kill(entireProcessTree: true);
    }
}
Console.WriteLine($"total accessibility errors: {failures}");
return failures > 0 ? 1 : 0;
