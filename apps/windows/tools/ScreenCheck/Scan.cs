using System.Text.Json;
using Axe.Windows.Automation;
using Axe.Windows.Automation.Data;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Definitions;
using FlaUI.Core.Input;
using FlaUI.Core.WindowsAPI;
using FlaUI.UIA3;

namespace Brasscribe.ScreenCheck;

/// <summary>
/// The checks that read a running window through UI Automation, from this process: the Axe.Windows rules, and a
/// walk with Tab (where the focus goes, whether every control is reached, whether it comes back round).
/// </summary>
internal static class Scan
{
    /// <summary>Tab presses before the walk gives up on coming back round.</summary>
    private const int MaxStops = 60;

    public static int Run(int pid, nint hwnd, string shot, string outFile)
    {
        var findings = new List<Finding>();
        findings.AddRange(Axe(pid, shot, Path.Combine(Path.GetDirectoryName(Path.GetFullPath(outFile))!, "axe")));
        findings.AddRange(Keyboard(pid, hwnd, shot, out var order));
        File.WriteAllText(outFile, JsonSerializer.Serialize(findings, JsonFiles.Options));
        File.WriteAllLines(Path.ChangeExtension(outFile, ".tab.txt"), order);
        foreach (var f in findings) Console.WriteLine(f);
        return 0;
    }

    /// <summary>Axe.Windows' rules on every window of the process: one finding per element and rule.</summary>
    public static IEnumerable<Finding> Axe(int pid, string shot, string outDir)
    {
        Directory.CreateDirectory(outDir);
        var config = Config.Builder.ForProcessId(pid).WithOutputDirectory(outDir).WithOutputFileFormat(OutputFileFormat.A11yTest).Build();
        var output = ScannerFactory.CreateScanner(config).Scan(new ScanOptions(scanId: shot));
        foreach (var window in output.WindowScanOutputs)
            foreach (var e in window.Errors)
            {
                var props = e.Element.Properties;
                string name = props is not null && props.TryGetValue("Name", out var n) ? n : "";
                string type = props is not null && props.TryGetValue("ControlType", out var t) ? t : "";
                yield return new Finding(shot, $"axe:{e.Rule.ID}", $"{type} \"{name}\"", e.Rule.Description);
            }
    }

    /// <summary>
    /// Presses Tab until the focus comes back to where it first landed. Findings: the focus on something not shown,
    /// no way back round (a trap, or more stops than <see cref="MaxStops"/>), and a control on screen that Tab never
    /// reaches (left out: list, tab and menu items and radio buttons, which the arrow keys reach inside their group).
    /// The focus must land in the window at the first press, or the walk could not run (an exception: exit 3).
    /// </summary>
    public static IEnumerable<Finding> Keyboard(int pid, nint hwnd, string shot, out List<string> order)
    {
        order = [];
        var findings = new List<Finding>();
        using var automation = new UIA3Automation();
        var window = automation.FromHandle(hwnd);
        Win.SetForegroundWindow(hwnd);
        Thread.Sleep(300);
        if (Win.GetForegroundWindow() != hwnd) throw new InvalidOperationException("the window could not be brought to the front for the walk with Tab");
        var bounds = window.BoundingRectangle;

        var seen = new HashSet<string>();
        var visited = new List<AutomationElement>();
        string? first = null;
        bool round = false;
        for (int i = 0; i < MaxStops; i++)
        {
            FlaUI.Core.Input.Keyboard.Type(VirtualKeyShort.TAB);
            Thread.Sleep(150);
            var focused = automation.FocusedElement();
            if (focused is null || focused.Properties.ProcessId.ValueOrDefault != pid)
            {
                if (i == 0) throw new InvalidOperationException("the first Tab did not land in the window");
                findings.Add(new Finding(shot, "keyboard", "the window", "Tab takes the focus out of the window"));
                break;
            }
            string id = Id(focused);
            if (id == first) { round = true; break; }
            first ??= id;
            seen.Add(id);
            visited.Add(focused);
            var r = focused.BoundingRectangle;
            order.Add($"{Describe(focused)} at {r.X},{r.Y} {r.Width}x{r.Height}");
            bool shown = !focused.Properties.IsOffscreen.ValueOrDefault && r.Width > 0 && r.Height > 0 && r.IntersectsWith(bounds);
            if (!shown) findings.Add(new Finding(shot, "keyboard", Describe(focused), "Tab lands on it while it is not shown"));
        }
        if (!round) findings.Add(new Finding(shot, "keyboard", "the window", $"Tab does not come back round within {MaxStops} stops"));

        // Every control on screen that takes the keyboard should be reached, within the part the walk went round: the
        // window, or an open dialog that keeps the focus in itself (what the stops have in common).
        var scope = CommonAncestor(visited) ?? window;
        foreach (var e in scope.FindAllDescendants())
        {
            if (!Reachable(e) || seen.Contains(Id(e))) continue;
            findings.Add(new Finding(shot, "keyboard", Describe(e), "Tab never reaches it"));
        }
        return findings;
    }

    private static readonly HashSet<ControlType> Controls =
        [ControlType.Button, ControlType.CheckBox, ControlType.ComboBox, ControlType.Edit, ControlType.Hyperlink, ControlType.Slider, ControlType.SplitButton];

    private static readonly HashSet<ControlType> Groups =
        [ControlType.List, ControlType.Tree, ControlType.Tab, ControlType.Menu, ControlType.MenuBar, ControlType.DataGrid, ControlType.Table];

    private static bool Reachable(AutomationElement e)
    {
        try
        {
            var p = e.Properties;
            if (!Controls.Contains(p.ControlType.ValueOrDefault) || !p.IsKeyboardFocusable.ValueOrDefault || !p.IsEnabled.ValueOrDefault
                || p.IsOffscreen.ValueOrDefault || e.BoundingRectangle.IsEmpty)
                return false;
            for (var up = e.Parent; up is not null; up = up.Parent)
                if (Groups.Contains(up.Properties.ControlType.ValueOrDefault)) return false;
            return true;
        }
        catch (Exception x) when (x is System.Runtime.InteropServices.COMException or FlaUI.Core.Exceptions.PropertyNotSupportedException)
        {
            return false; // gone while it was read
        }
    }

    /// <summary>The innermost element that holds every stop of the walk (by their chains of parents).</summary>
    private static AutomationElement? CommonAncestor(List<AutomationElement> stops)
    {
        List<AutomationElement>? common = null;
        foreach (var stop in stops)
        {
            var chain = new List<AutomationElement>();
            try { for (var up = stop.Parent; up is not null; up = up.Parent) chain.Insert(0, up); }
            catch (System.Runtime.InteropServices.COMException) { continue; }
            if (common is null) { common = chain; continue; }
            int n = 0;
            while (n < common.Count && n < chain.Count && Id(common[n]) == Id(chain[n])) n++;
            common = common[..n];
        }
        return common is { Count: > 0 } ? common[^1] : null;
    }

    private static string Id(AutomationElement e) => string.Join(".", e.Properties.RuntimeId.ValueOrDefault ?? []);

    private static string Describe(AutomationElement e) =>
        $"{e.Properties.ControlType.ValueOrDefault} \"{e.Properties.Name.ValueOrDefault}\"";
}
