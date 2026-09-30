using Brasscribe.Play.Core.Playback;

namespace Brasscribe.Play.Core.ViewModels;

/// <summary>
/// Puts the app on one screen with sample content, without a recording or Brasscribe on your
/// computer: for screenshots of every screen (the CI workflow starts the app with --show NAME) and
/// for looking at a screen while working on it. The score screens use a MusicXML score passed in
/// (the CI passes apps/fixtures/old-hundredth/brass-band.musicxml, which carries review marks).
/// </summary>
public static class PreviewScenes
{
    public static readonly string[] Names =
        ["first-run", "what-do-you-play", "home", "home-offline", "settings", "what-is-this", "transcribing", "review", "review-listening", "choose-output", "score", "part", "stand", "export", "error"];

    /// <summary>The computer in the sample scenes.</summary>
    public const string SampleServer = "Brasscribe on Studio PC";

    /// <summary>The piece in the sample scenes: the public-domain fixture in apps/fixtures/old-hundredth.</summary>
    public const string SampleTitle = "Old Hundredth";

    /// <summary>Shows <paramref name="scene"/>. Returns false for an unknown name or a score scene without a score.</summary>
    public static bool Show(MainViewModel main, string scene, string? scorePath)
    {
        // A made-up file for the "What is this?" screen: the scenes never read it.
        var sample = new SourceAudio(Path.Combine(Path.GetTempPath(), "Band practice.m4a"), "Band practice.m4a", new TimeSpan(0, 3, 5), null, false);
        if (scene is not ("first-run" or "what-do-you-play")) main.Settings.FirstRunDone = true;
        // A fixed connection row: the scenes never talk to a computer.
        main.Settings.Connection.Show(scene == "home-offline" ? Engine.ConnectionState.Offline : Engine.ConnectionState.Connected, SampleServer);
        switch (scene)
        {
            case "first-run":
                main.Screen = Screen.FirstRun;
                return true;
            case "what-do-you-play":
                // "Get started" on a profile with no instrument chosen asks the question (when the core has the seats)
                main.GetStartedCommand.Execute(null);
                return true;
            case "home" or "home-offline" or "settings":
                // the shell opens Settings over Home for "settings"
                main.Screen = Screen.Start;
                return true;
            case "what-is-this":
                main.Kind.Source = sample;
                main.Kind.SetWhere(main.Settings.EngineUri);
                main.Kind.Selected = main.Kind.Options.FirstOrDefault(o => o.Kind == SourceKind.OrchestraWithSoloist);
                main.Screen = Screen.SourceKind;
                return true;
            case "transcribing":
                main.Kind.SetWhere(main.Settings.EngineUri);
                main.Transcription.ShowProgress(SampleTitle, "orchestra-with-soloist",
                    main.Kind.Options.First(o => o.Kind == SourceKind.OrchestraWithSoloist).Label, "Notes", 62, TimeSpan.FromMinutes(2));
                main.Screen = Screen.Transcribing;
                return true;
            case "error":
                main.Transcription.ShowProgress(SampleTitle, "orchestra-with-soloist", "", "Ready", 0, null);
                main.Error.Show(ErrorKind.ComputerUnreachable, "The engine at http://127.0.0.1:8765/ could not be reached.");
                main.Screen = Screen.Error;
                return true;
        }
        if (scorePath is null || !File.Exists(scorePath) || !Names.Contains(scene)) return false;
        main.OpenScoreFile(scorePath);
        switch (scene)
        {
            case "review":
                main.CheckNotesCommand.Execute(null);
                break;
            case "review-listening":
                main.CheckNotesCommand.Execute(null);
                main.Score.PreviewListening();
                break;
            case "choose-output":
                main.Screen = Screen.ChooseOutput;
                break;
            case "part":
                main.Score.SelectedPartIndex = 0;
                break;
            case "score" or "export" or "stand":
                if (main.Score.Player.BarCount >= 2)
                {
                    main.Score.Player.LoopStart = 2;
                    main.Score.Player.LoopEnd = Math.Min(3, main.Score.Player.BarCount);
                    main.Score.Player.SetLoopCommand.Execute(null);
                }
                break;
        }
        return true;
    }
}
