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

    public App()
    {
        AppDomain.CurrentDomain.UnhandledException += (_, e) => WriteCrash(e.ExceptionObject as Exception);
        UnhandledException += OnUnhandledException;
        TaskScheduler.UnobservedTaskException += (_, e) =>
        {
            WriteCrash(e.Exception);
            e.SetObserved();
        };
        var settings = new JsonSettingsStore();
        string language = Option("--lang") ?? settings.Get("Language", "system");
        if (language != "system")
        {
            Microsoft.Windows.Globalization.ApplicationLanguages.PrimaryLanguageOverride = language;
            // .NET formats with its own culture: the chosen language also decides key and pitch names, dates and
            // percentages, or a Norwegian app on an English Windows would mix the two.
            try
            {
                var culture = System.Globalization.CultureInfo.GetCultureInfo(language);
                System.Globalization.CultureInfo.DefaultThreadCurrentCulture = culture;
                System.Globalization.CultureInfo.DefaultThreadCurrentUICulture = culture;
                System.Globalization.CultureInfo.CurrentCulture = culture;
                System.Globalization.CultureInfo.CurrentUICulture = culture;
            }
            catch (System.Globalization.CultureNotFoundException) { }
        }
        InitializeComponent();
        Settings = settings;
    }

    /// <summary>
    /// The last line of defence for an exception nothing else caught (an event handler, a command, an
    /// async void): it is logged, and unless the process is in a state it cannot go on from, the app
    /// stays open and says that something went wrong.
    /// </summary>
    private void OnUnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
    {
        WriteCrash(e.Exception);
        if (IsFatal(e.Exception)) return;
        e.Handled = true;
        _window?.DispatcherQueue.TryEnqueue(() => _window?.ShowProblem());
    }

    private static bool IsFatal(Exception? e) =>
        e is null or OutOfMemoryException or AccessViolationException or StackOverflowException or InvalidProgramException
            or BadImageFormatException or System.Runtime.InteropServices.SEHException;

    /// <summary>An unhandled exception, appended to crash.log next to settings.json (read by the CI smoke test).</summary>
    private static void WriteCrash(Exception? e)
    {
        try
        {
            var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Brasscribe", "Play");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "crash.log"), $"{DateTimeOffset.Now:O} {e}{Environment.NewLine}");
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    /// <summary>The value after a command-line switch ("--show score" gives "score").</summary>
    private static string? Option(string name)
    {
        var args = Environment.GetCommandLineArgs();
        int i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    /// <summary>Strings for code-behind; view models receive <see cref="IStrings"/> through their constructors.</summary>
    /// <remarks>Made on first use, after the constructor has set the language: a loader made before that (a static
    /// initialiser runs before the constructor) may keep Windows' language.</remarks>
    public static IStrings Strings => _strings ??= new ResourceStrings();

    private static IStrings? _strings;

    public static MainWindow? MainWindowInstance => (Current as App)?._window;

    internal JsonSettingsStore Settings { get; }

    /// <summary>Settings › Display › Appearance on every window (design/system.md §10).</summary>
    internal ThemeController? Theme { get; private set; }

    /// <summary>Other launches with a pairing link are sent to the running app under this key.</summary>
    private const string InstanceKey = "BrasscribePlay";

    /// <summary>
    /// The screen catalogue (tests/Brasscribe.Play.Catalogue) takes over the start here when the app is built as its
    /// test host (-p:BrasscribeCatalogue=true); in the app itself this has no body and is compiled away.
    /// </summary>
    static partial void RunCatalogue(App app, ref bool handled);

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        bool catalogue = false;
        RunCatalogue(this, ref catalogue);
        if (catalogue) return;

        bool preview = Option("--show") is not null;
        // A brasscribe://pair link while the app already runs: hand it to that window and quit.
        string? pairingLink = PairingLinkFromLaunch();
        if (!preview && await RedirectToRunningAppAsync(pairingLink)) return;

        var queue = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();
        // --theme light|dark|pink-light|pink-dark: a fixed theme for screenshots; otherwise the Appearance setting decides.
        var (main, settingsVm) = Compose(Settings, JsonSettingsStore.WorkDirectory, Option("--theme"));
        var window = _window!;
        window.HeartbeatEnabled = !preview;
        window.Activate();

        if (!preview)
        {
            settingsVm.Connection.Start();
            System.Net.NetworkInformation.NetworkChange.NetworkAddressChanged += (_, _) => queue.TryEnqueue(settingsVm.Connection.Kick);
            RegisterPairingLinks(queue);
            if (pairingLink is not null)
                window.DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, async () => await window.OpenSettingsAsync(pairingLink));
        }

        // --show NAME [--score FILE]: one screen with sample content, for screenshots (see PreviewScenes).
        if (Option("--show") is { } scene)
        {
            // "settings": Home with Settings open.
            if (PreviewScenes.Show(main, scene == "settings" ? "home" : scene, Option("--score")) && scene is "export" or "settings")
                window.DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, async () =>
                {
                    await Task.Delay(1500);
                    await (scene == "export" ? window.ShowExportAsync() : window.OpenSettingsAsync());
                });
            return;
        }

        // "Open with" and the command line: open the file directly.
        if (pairingLink is not null) return;
        var cli = Environment.GetCommandLineArgs().Skip(1).FirstOrDefault(File.Exists);
        if (cli is not null) _ = main.Start.OpenPathAsync(cli);
    }

    /// <summary>
    /// The view models over this PC's services and the window that shows them, with Settings › Appearance on it: the
    /// app's window and <see cref="Theme"/> from now on. Nothing starts talking to a computer yet. The screen catalogue
    /// composes a window like this for each of its screens, with settings kept in memory.
    /// </summary>
    /// <param name="forcedTheme">"--theme": wins over the stored Appearance (never over a contrast theme).</param>
    internal (MainViewModel Main, SettingsViewModel Settings) Compose(ISettingsStore settings, string workDirectory, string? forcedTheme)
    {
        MainWindow? window = null;
        var queue = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();
        var ui = new DispatcherQueueDispatcher(queue);
        var announcer = new UiaAnnouncer(() => window?.AnnouncerHost, queue);
        var dialogs = new WinFileDialogs(() => window is null ? 0 : WinRT.Interop.WindowNative.GetWindowHandle(window));
        var core = CoreBridge.Create();

        var synthOut = new BufferedSynthOutput();
        var player = new AlphaTabScorePlayer(synthOut);
        LoadSoundFonts(player);
        // The output device opens when the band plays, and follows Windows' default device. Without one the
        // app still works for reading and exports, and playing starts once a device appears.
        var audioOut = new WasapiSynthOutput();
        audioOut.Start(synthOut);

        var original = new MediaPlayerOriginal(queue);
        var playerVm = new PlayerViewModel(player, announcer, Strings, ui);
        var score = new ScoreViewModel(core, playerVm, announcer, Strings, original)
        {
            Language = Microsoft.Windows.Globalization.ApplicationLanguages.Languages.FirstOrDefault()?.StartsWith("nb", StringComparison.OrdinalIgnoreCase) == true
                       || System.Globalization.CultureInfo.CurrentUICulture.TwoLetterISOLanguageName is "nb" or "no" or "nn" ? "nb" : "en",
        };
        // Heartbeats and pairing share one client with short timeouts; the credential is in the Credential Locker.
        var shortHttp = new HttpClient(new SocketsHttpHandler { ConnectTimeout = TimeSpan.FromSeconds(4) }) { Timeout = TimeSpan.FromSeconds(15) };
        // RequestedTheme is never set by the app, so it is Windows' app mode at start-up.
        var settingsVm = new SettingsViewModel(settings, announcer, Strings, vault: CredentialLockerVault.Create(),
            clients: (uri, token) => new EngineClient(shortHttp, uri) { Token = token }, systemDark: RequestedTheme == ApplicationTheme.Dark);

        // No overall timeout (the event stream stays open for the whole job), but a LAN address that
        // drops packets must fail within seconds rather than hang on connect.
        IEngineClient EngineFactory(Uri uri, string? token) =>
            new EngineClient(new HttpClient(new SocketsHttpHandler { ConnectTimeout = TimeSpan.FromSeconds(10) })
            {
                Timeout = Timeout.InfiniteTimeSpan,
            }, uri) { Token = token };

        MainViewModel? main = null;
        main = new MainViewModel(
            new StartViewModel(new WasapiCaptureService(), new MediaFoundationDecoder(), dialogs, announcer, Strings, ui, workDirectory),
            new SourceKindViewModel(Strings),
            new TranscriptionViewModel(() => main!.Engine, announcer, Strings, ui),
            score,
            new ExportViewModel(new ExportService(), dialogs, announcer, Strings, new ShellPdfPrinter()),
            new OutputOptionsViewModel(core, announcer, Strings),
            settingsVm,
            EngineFactory, announcer, Strings, core,
            new ScoreLibrary(System.IO.Path.Combine(workDirectory, "library")))
        {
            LayerCacheRoot = System.IO.Path.Combine(workDirectory, "layers"),
        };

        Theme = new ThemeController(settingsVm, queue, forcedTheme);
        window = new MainWindow(main, Strings);
        Theme.Attach(window);
        window.Closed += (_, _) =>
        {
            audioOut.Dispose();
            player.Dispose();
            original.Dispose();
        };
        _window = window;
        return (main, settingsVm);
    }

    /// <summary>A brasscribe://pair link this launch was started with (protocol activation, or on the command line).</summary>
    private static string? PairingLinkFromLaunch()
    {
        try
        {
            var activated = Microsoft.Windows.AppLifecycle.AppInstance.GetCurrent().GetActivatedEventArgs();
            if (LinkFrom(activated) is { } link) return link;
        }
        catch (Exception e) when (e is System.Runtime.InteropServices.COMException or InvalidOperationException) { }
        return Environment.GetCommandLineArgs().Skip(1).Select(LinkIn).FirstOrDefault(l => l is not null);
    }

    private static string? LinkFrom(Microsoft.Windows.AppLifecycle.AppActivationArguments activated) => activated.Data switch
    {
        Windows.ApplicationModel.Activation.IProtocolActivatedEventArgs p => p.Uri.OriginalString,
        Windows.ApplicationModel.Activation.ILaunchActivatedEventArgs l => LinkIn(l.Arguments),
        _ => null,
    };

    private static string? LinkIn(string? text)
    {
        if (string.IsNullOrEmpty(text)) return null;
        int at = text.IndexOf(Core.Engine.PairingLink.Scheme + ":", StringComparison.OrdinalIgnoreCase);
        return at < 0 ? null : text[at..].Trim().Trim('"').Split(' ')[0].Trim('"');
    }

    /// <summary>
    /// With a pairing link and another Brasscribe Play already running, the link goes to that window and
    /// this process ends. Plain launches are not redirected (each may open a file of its own).
    /// </summary>
    private static async Task<bool> RedirectToRunningAppAsync(string? pairingLink)
    {
        try
        {
            var keyed = Microsoft.Windows.AppLifecycle.AppInstance.FindOrRegisterForKey(InstanceKey);
            if (keyed.IsCurrent || pairingLink is null) return false;
            await keyed.RedirectActivationToAsync(Microsoft.Windows.AppLifecycle.AppInstance.GetCurrent().GetActivatedEventArgs());
            Environment.Exit(0);
            return true;
        }
        catch (Exception e) when (e is System.Runtime.InteropServices.COMException or InvalidOperationException)
        {
            return false;
        }
    }

    /// <summary>brasscribe:// opens this app (per user, no installer needed), and links sent from another launch arrive here.</summary>
    private void RegisterPairingLinks(Microsoft.UI.Dispatching.DispatcherQueue queue)
    {
        try
        {
            Microsoft.Windows.AppLifecycle.AppInstance.GetCurrent().Activated += (_, activated) =>
            {
                if (LinkFrom(activated) is not { } link) return;
                queue.TryEnqueue(async () =>
                {
                    if (_window is null) return;
                    _window.Activate();
                    await _window.OpenSettingsAsync(link);
                });
            };
        }
        catch (Exception e) when (e is System.Runtime.InteropServices.COMException or InvalidOperationException) { }

        string? exe = Environment.ProcessPath;
        if (exe is null) return;
        _ = Task.Run(() =>
        {
            try
            {
                Microsoft.Windows.AppLifecycle.ActivationRegistrationManager.RegisterForProtocolActivation(
                    Core.Engine.PairingLink.Scheme, "", Strings["AppWindowTitle"], exe);
            }
            catch (Exception e) when (e is System.Runtime.InteropServices.COMException or InvalidOperationException or UnauthorizedAccessException) { }
        });
    }

    /// <summary>
    /// Loads the band SoundFont with its part map (SoundFonts\brasscribe-band.sf2 + mapping.json):
    /// a preset and a level per part, drums on channel 10. Without it, the per-instrument SoundFonts
    /// under SoundFonts\built are used, one program pair per instrument.
    /// </summary>
    private static void LoadSoundFonts(AlphaTabScorePlayer player)
    {
        var dir = Path.Combine(AppContext.BaseDirectory, "SoundFonts");
        string band = Path.Combine(dir, "brasscribe-band.sf2"), map = Path.Combine(dir, "mapping.json");
        if (File.Exists(band) && File.Exists(map)) _ = BandSoundFont.Load(map, band).ApplyTo(player, inBackground: true);
        else if (Directory.Exists(Path.Combine(dir, "built"))) _ = BrassSoundSet.Load(Path.Combine(dir, "built"), map).ApplyTo(player, inBackground: true);
        else
        {
            player.SoundsMissingFrom = band;
            System.Diagnostics.Trace.TraceWarning($"No band SoundFont at {band}: playback has no instrument sounds");
        }
    }
}
