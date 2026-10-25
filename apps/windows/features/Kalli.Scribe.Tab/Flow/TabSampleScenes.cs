using Kalli.Scribe.Engine;
using Kalli.Scribe.Scores;
using Kalli.Scribe.ViewModels;

namespace Kalli.Scribe.Tab;

/// <summary>
/// Puts a tab app on one screen with sample content, without a recording or the computer: for screenshots of every
/// screen (the CI workflow starts the app with --show NAME, the screen catalogue calls it) and for looking at a screen
/// while working on it. The tab screens read a tab fixture folder (tab.musicxml, tab.json, job.json, composition.json),
/// the public-domain apps/fixtures/guitar-line.
/// </summary>
public static class TabSampleScenes
{
    public static readonly string[] Names =
        ["first-run", "your-instrument", "home", "home-offline", "home-update", "what-is-this", "what-is-this-offline", "transcribing",
         "check-the-song", "tab", "error", "error-update"];

    /// <summary>The computer in the sample scenes.</summary>
    public const string SampleServer = ServerNames.Prefix + "Studio PC";

    /// <summary>The song in the sample scenes.</summary>
    public const string SampleTitle = "Guitar line";

    /// <summary>Shows <paramref name="scene"/>. False for an unknown name, or a tab scene without the fixture.</summary>
    public static async Task<bool> ShowAsync(TabFlowViewModel flow, string scene, string? fixture)
    {
        // A made-up recording for What is this?: the scenes never read it.
        var sample = new SourceAudio(Path.Combine(Path.GetTempPath(), "Guitar line.m4a"), "Guitar line.m4a", new TimeSpan(0, 0, 42), null, false);
        if (scene != "first-run") flow.Settings.FirstRunDone = true;
        // A fixed connection row: the scenes never talk to a computer.
        flow.Settings.Connection.Show(scene switch
        {
            "home-offline" or "what-is-this-offline" => ConnectionState.Offline,
            "home-update" or "error-update" => ConnectionState.UpdateBandroom,
            _ => ConnectionState.Connected,
        }, SampleServer);
        switch (scene)
        {
            case "first-run":
                flow.Screen = TabScreen.FirstRun;
                return true;
            case "your-instrument":
                flow.ChangeInstrumentCommand.Execute(null);
                return true;
            case "home" or "home-offline" or "home-update":
                flow.Screen = TabScreen.Home;
                return true;
            case "what-is-this" or "what-is-this-offline":
                flow.ShowWhatIsThis(sample, listed: new HashSet<string> { TabProfiles.Tab });
                return true;
            case "transcribing":
                flow.Transcription.ShowProgress(SampleTitle, TabProfiles.Tab, "", "Notes", 62, TimeSpan.FromMinutes(1));
                flow.Screen = TabScreen.Transcribing;
                return true;
            case "error":
                flow.Transcription.ShowProgress(SampleTitle, TabProfiles.Tab, "", "Ready", 0, null);
                flow.Error.Show(ErrorKind.ComputerUnreachable, "The engine at http://127.0.0.1:8765/ could not be reached.");
                flow.Screen = TabScreen.Error;
                return true;
            case "error-update":
                flow.Transcription.ShowProgress(SampleTitle, TabProfiles.Tab, "", "Ready", 0, null);
                flow.Error.Show(ErrorKind.UpdateBandroom, InterfaceMatch.Details(Wire.InterfaceVersion - 1));
                flow.Screen = TabScreen.Error;
                return true;
        }
        if (fixture is null || !Names.Contains(scene)) return false;
        string Read(string file) => File.ReadAllText(Path.Combine(fixture, file));
        if (!File.Exists(Path.Combine(fixture, "tab.musicxml")) || !File.Exists(Path.Combine(fixture, "tab.json"))) return false;
        var tab = TabResult.Parse(Read("tab.json"));
        if (tab is null) return false;
        var composition = File.Exists(Path.Combine(fixture, "composition.json")) ? CompositionJson.Parse(Read("composition.json")) : null;
        switch (scene)
        {
            case "check-the-song":
                var stages = File.Exists(Path.Combine(fixture, "job.json"))
                    ? [.. System.Text.Json.JsonDocument.Parse(Read("job.json")).RootElement.GetProperty("stages").EnumerateArray()
                        .Select(s => s.GetProperty("name").GetString() ?? "")]
                    : new List<string>();
                flow.ShowCheck(tab, stages);
                return true;
            case "tab":
                await flow.ShowTabAsync(Read("tab.musicxml"), tab, composition, SampleTitle);
                return true;
        }
        return false;
    }
}
