using Brasscribe.Play.Audio.Windows;
using Brasscribe.Play.Core.Bridge;
using Brasscribe.Play.Core.Engine;
using Brasscribe.Play.Core.Export;
using Brasscribe.Play.Core.Playback;
using Brasscribe.Play.Core.Services;
using Brasscribe.Play.Core.ViewModels;
using Brasscribe.Play.Services;
using Microsoft.UI.Xaml;

namespace Brasscribe.Play;

/// <summary>Composition root: platform services, view models and the main window.</summary>
public partial class App : Application
{
    private MainWindow? _window;
    private WasapiSynthOutput? _audioOut;

    public App()
    {
        var settings = new JsonSettingsStore();
        string language = settings.Get("Language", "system");
        if (language != "system")
            Microsoft.Windows.Globalization.ApplicationLanguages.PrimaryLanguageOverride = language;
        InitializeComponent();
        Settings = settings;
    }

    /// <summary>Strings for code-behind; view models receive <see cref="IStrings"/> through their constructors.</summary>
    public static IStrings Strings { get; } = new ResourceStrings();

    public static MainWindow? MainWindowInstance => (Current as App)?._window;

    internal JsonSettingsStore Settings { get; }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        var queue = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();
        var ui = new DispatcherQueueDispatcher(queue);
        var announcer = new UiaAnnouncer(() => _window?.AnnouncerHost, queue);
        var dialogs = new WinFileDialogs(() => _window is null ? 0 : WinRT.Interop.WindowNative.GetWindowHandle(_window));
        var core = CoreBridge.Create();

        var synthOut = new BufferedSynthOutput();
        var player = new AlphaTabScorePlayer(synthOut);
        LoadSoundFonts(player);
        _audioOut = new WasapiSynthOutput();
        try { _audioOut.Start(synthOut); }
        catch (Exception e) when (e is System.Runtime.InteropServices.COMException or InvalidOperationException)
        {
            // No output device: the app still works for reading and exports.
        }

        var original = new MediaPlayerOriginal();
        var playerVm = new PlayerViewModel(player, announcer, Strings, ui);
        var score = new ScoreViewModel(core, playerVm, announcer, Strings, original)
        {
            Language = Microsoft.Windows.Globalization.ApplicationLanguages.Languages.FirstOrDefault()?.StartsWith("nb", StringComparison.OrdinalIgnoreCase) == true
                       || System.Globalization.CultureInfo.CurrentUICulture.TwoLetterISOLanguageName is "nb" or "no" or "nn" ? "nb" : "en",
        };
        var settingsVm = new SettingsViewModel(Settings, announcer, Strings);

        // No overall timeout (the event stream stays open for the whole job), but a LAN address that
        // drops packets must fail within seconds rather than hang on connect.
        IEngineClient EngineFactory(Uri uri, string? token) =>
            new EngineClient(new HttpClient(new SocketsHttpHandler { ConnectTimeout = TimeSpan.FromSeconds(10) })
            {
                Timeout = Timeout.InfiniteTimeSpan,
            }, uri) { Token = token };

        MainViewModel? main = null;
        main = new MainViewModel(
            new StartViewModel(new WasapiCaptureService(), new MediaFoundationDecoder(), dialogs, announcer, Strings, ui, JsonSettingsStore.WorkDirectory),
            new SourceKindViewModel(Strings),
            new TranscriptionViewModel(() => main!.Engine, announcer, Strings, ui),
            score,
            new ExportViewModel(new ExportService(), dialogs, announcer, Strings),
            new OutputOptionsViewModel(core, announcer, Strings),
            settingsVm,
            EngineFactory, announcer, Strings, core);

        _window = new MainWindow(main, Strings);
        _window.Closed += (_, _) =>
        {
            _audioOut?.Dispose();
            player.Dispose();
            original.Dispose();
        };
        _window.Activate();

        // "Open with" and the command line: open the file directly.
        var cli = Environment.GetCommandLineArgs().Skip(1).FirstOrDefault(File.Exists);
        if (cli is not null) _ = main.Start.OpenPathAsync(cli);
    }

    /// <summary>
    /// Loads the baseline brass SoundFonts shipped next to the exe (SoundFonts\&lt;instrument&gt;\*.sf2),
    /// one program pair per instrument, and routes each part to its instrument.
    /// </summary>
    private static void LoadSoundFonts(AlphaTabScorePlayer player)
    {
        var dir = Path.Combine(AppContext.BaseDirectory, "SoundFonts");
        if (Directory.Exists(dir)) BrassSoundSet.Load(dir).ApplyTo(player);
    }
}
