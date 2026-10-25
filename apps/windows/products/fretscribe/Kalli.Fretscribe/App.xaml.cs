using Kalli.Scribe.Audio.Windows;
using Kalli.Scribe.Controls;
using Kalli.Scribe.Engine;
using Kalli.Scribe.Services;
using Kalli.Scribe.Tab;
using Kalli.Scribe.ViewModels;
using Kalli.Scribe.WinUI;
using Kalli.Fretscribe.Services;
using Microsoft.UI.Xaml;

namespace Kalli.Fretscribe;

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
        var settings = new JsonSettingsStore(Product.Folder);
        string language = Option("--lang") ?? settings.Get("Language", "system");
        if (language != "system")
        {
            Microsoft.Windows.Globalization.ApplicationLanguages.PrimaryLanguageOverride = language;
            // .NET formats with its own culture: the chosen language also decides key names, dates and percentages.
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
    /// The last line of defence for an exception nothing else caught: it is logged, and unless the process is in a
    /// state it cannot go on from, the app stays open and says that something went wrong.
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
            Directory.CreateDirectory(Product.Folder.Root);
            File.AppendAllText(Product.Folder.CrashLog, $"{DateTimeOffset.Now:O} {e}{Environment.NewLine}");
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    /// <summary>The value after a command-line switch ("--show tab" gives "tab").</summary>
    private static string? Option(string name)
    {
        var args = Environment.GetCommandLineArgs();
        int i = Array.IndexOf(args, name);
        return i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
    }

    /// <summary>Strings for code-behind; view models receive <see cref="IStrings"/> through their constructors.</summary>
    public static IStrings Strings { get; } = new ResourceStrings();

    public static MainWindow? MainWindowInstance => (Current as App)?._window;

    internal JsonSettingsStore Settings { get; }

    /// <summary>Settings › Appearance on every window.</summary>
    internal ThemeController? Theme { get; private set; }

    /// <summary>
    /// The screen catalogue (products/fretscribe/Kalli.Fretscribe.Catalogue) takes over the start here when the app is
    /// built as its test host (-p:ScribeCatalogue=true); in the app itself this has no body and is compiled away.
    /// </summary>
    static partial void RunCatalogue(App app, ref bool handled);

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        bool catalogue = false;
        RunCatalogue(this, ref catalogue);
        if (catalogue) return;

        bool preview = Option("--show") is not null;
        // A scribe://pair link while the app already runs: hand it to that window and quit.
        string? pairingLink = PairingLinkFromLaunch();
        if (!preview && await RedirectToRunningAppAsync(pairingLink)) return;

        var queue = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();
        // --theme light|dark: a fixed theme for screenshots; otherwise the Appearance setting decides.
        var (flow, settingsVm) = Compose(Settings, Product.Folder.Work, Option("--theme"));
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

        // --show NAME [--score DIR]: one screen with sample content, for screenshots (see TabSampleScenes); DIR is a tab fixture folder.
        if (Option("--show") is { } scene)
        {
            if (await TabSampleScenes.ShowAsync(flow, scene is "settings" or "help" ? "home" : scene, Option("--score")) && scene is "settings" or "export" or "help")
                window.DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, async () =>
                {
                    await Task.Delay(1500);
                    await (scene switch { "export" => window.ShowExportAsync(), "help" => window.ShowHelpAsync(), _ => window.OpenSettingsAsync() });
                });
            return;
        }

        // "Open with" and the command line: open the file directly.
        if (pairingLink is not null) return;
        var cli = Environment.GetCommandLineArgs().Skip(1).FirstOrDefault(File.Exists);
        if (cli is not null) _ = flow.Start.OpenPathAsync(cli);
    }

    /// <summary>
    /// The view models over this PC's services and the window that shows them, with Settings › Appearance on it: the
    /// app's window and <see cref="Theme"/> from now on. Nothing starts talking to a computer yet. The screen catalogue
    /// composes a window like this for each of its screens, with settings kept in memory.
    /// </summary>
    /// <param name="forcedTheme">"--theme": wins over the stored Appearance (never over a contrast theme).</param>
    internal (TabFlowViewModel Flow, SettingsViewModel Settings) Compose(ISettingsStore settings, string workDirectory, string? forcedTheme)
    {
        MainWindow? window = null;
        var queue = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();
        var ui = new DispatcherQueueDispatcher(queue);
        var announcer = new UiaAnnouncer(() => window?.AnnouncerHost, queue);
        var dialogs = new WinFileDialogs(() => window is null ? 0 : WinRT.Interop.WindowNative.GetWindowHandle(window));

        // Heartbeats and pairing share one client with short timeouts; the credential is in the Credential Locker.
        var shortHttp = new HttpClient(new SocketsHttpHandler { ConnectTimeout = TimeSpan.FromSeconds(4) }) { Timeout = TimeSpan.FromSeconds(15) };
        // RequestedTheme is never set by the app, so it is Windows' app mode at start-up.
        var settingsVm = new SettingsViewModel(settings, announcer, Strings, vault: CredentialLockerVault.Create(Product.Name, Product.Folder),
            clients: (uri, token) => new EngineClient(shortHttp, uri) { Token = token });

        // No overall timeout (the event stream stays open for the whole job), but a LAN address that drops packets must
        // fail within seconds rather than hang on connect.
        IEngineClient EngineFactory(Uri uri, string? token) =>
            new EngineClient(new HttpClient(new SocketsHttpHandler { ConnectTimeout = TimeSpan.FromSeconds(10) })
            {
                Timeout = Timeout.InfiniteTimeSpan,
            }, uri) { Token = token };

        var practice = new PracticeModel(new PracticeRecordings(Path.Combine(workDirectory, "recordings")),
            new PracticePlaces(Path.Combine(workDirectory, "places")), new MediaRecordingPlayers(queue));
        TabFlowViewModel? flow = null;
        flow = new TabFlowViewModel(Product.Target,
            new StartViewModel(new WasapiCaptureService(), new MediaFoundationDecoder(), dialogs, announcer, Strings, ui, workDirectory),
            new TranscriptionViewModel(() => flow!.Engine, announcer, Strings, ui),
            settingsVm, new YourInstrumentStore(settings), practice, new TabExportViewModel(dialogs, new ShellPdfPrinter(), announcer, Strings),
            EngineFactory, announcer, Strings,
            new ScoreLibrary(Path.Combine(workDirectory, "library")), new KeptTakes(Path.Combine(workDirectory, "kept")));

        Theme = new ThemeController(settingsVm, queue, forcedTheme);
        window = new MainWindow(flow, Strings);
        Theme.Attach(window);
        window.Closed += (_, _) => flow.TabPage.Dispose();
        _window = window;
        return (flow, settingsVm);
    }

    /// <summary>A scribe://pair link this launch was started with (protocol activation, or on the command line).</summary>
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

    private static string? LinkIn(string? text) => PairingLink.In(text);

    /// <summary>
    /// With a pairing link and another Fretscribe already running, the link goes to that window and this process ends.
    /// Plain launches are not redirected (each may open a file of its own).
    /// </summary>
    private static async Task<bool> RedirectToRunningAppAsync(string? pairingLink)
    {
        try
        {
            var keyed = Microsoft.Windows.AppLifecycle.AppInstance.FindOrRegisterForKey(Product.InstanceKey);
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

    /// <summary>
    /// Links sent from another launch arrive here. scribe:// itself is not registered by this app: the link names the
    /// family, and the app that registered it last on this PC would take every link; Fretscribe is paired from its
    /// own Settings, with the code or the link pasted there.
    /// </summary>
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
    }
}
