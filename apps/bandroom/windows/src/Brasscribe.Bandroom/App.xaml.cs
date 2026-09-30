using System.Diagnostics;
using Brasscribe.Bandroom.Core;
using Brasscribe.Bandroom.Core.Appearance;
using Brasscribe.Bandroom.Core.Engine;
using Brasscribe.Bandroom.Core.Downloads;
using Brasscribe.Bandroom.Core.Pairing;
using Brasscribe.Bandroom.Core.State;
using Brasscribe.Bandroom.Core.Supervisor;
using Brasscribe.Bandroom.Core.ViewModels;
using Brasscribe.Bandroom.Platform;
using Brasscribe.Bandroom.Views;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.Windows.AppLifecycle;

namespace Brasscribe.Bandroom;

/// <summary>
/// Composition root. No main window: the notification-area icon opens the flyout. Starts and supervises
/// the engine, runs the first-run setup, polls status, and routes phones asking to pair.
///
/// Command line: --background (the sign-in start), --demo (sample content, no engine), --show
/// flyout|devices|confirm-stop|window|pair|allow|settings (one view with sample content, for screenshots and
/// the accessibility scan), --state running|busy|attention|stopped|error|setup|starting, --theme light|dark
/// (for this run only; Settings › Appearance is the user's choice), --lang en|nb.
/// </summary>
public partial class App : Application, IBandroomActions, IPanelHost, ISettingsHost, IAnnouncer
{
    private readonly string[] _args = Environment.GetCommandLineArgs();
    private readonly IStrings _s;
    private readonly string? _theme;
    private readonly bool _demo;
    private DispatcherQueue _ui = null!;
    private TrayIcon? _tray;
    private FlyoutViewModel _vm = null!;
    private FlyoutWindow? _flyout;
    private PanelWindow? _window;
    private PairWindow? _pairWindow;
    /// <summary>Allow windows of their own (the Pair window closed), by request id: told when a request lapses.</summary>
    private readonly Dictionary<string, AllowRequestViewModel> _allowWindows = [];
    private SettingsWindow? _settingsWindow;
    private Windows.UI.ViewManagement.AccessibilitySettings _accessibility = null!;
    private AppearanceViewModel _appearance = null!;
    private ThemedWindows _themes = null!;
    private DemoEngine? _demoEngine;
    private EngineSupervisor? _supervisor;
    private BandroomController? _controller;
    private Bootstrapper? _bootstrap;
    private JobObjectLauncher? _launcher;
    private readonly StartupRegistration _startup = new();
    private readonly CancellationTokenSource _quit = new();
    private BandroomPaths _paths = BandroomPaths.ForCurrentUser();
    private EngineLog? _log;
    private bool _cuda;
    private ModelDownloader? _downloads;
    /// <summary>Setup and updates: one at a time.</summary>
    private readonly SingleFlight _setup = new();
    private string _hub = "";
    private EngineLaunchConfig? _config;
    private ComputerNameStore? _nameStore;
    private string? _customName;
    private readonly string _systemName = Machine.ComputerName();
    /// <summary>A new name or key reaches the engine with a restart, done once nothing is being made.</summary>
    private bool _restartWhenIdle;

    public App()
    {
        AppDomain.CurrentDomain.UnhandledException += (_, e) => WriteCrash(e.ExceptionObject as Exception);
        // An exception on the UI thread would end the app, and with it the engine in the middle of a score: log it
        // and carry on, unless the process can't.
        UnhandledException += (_, e) =>
        {
            WriteCrash(e.Exception);
            e.Handled = !IsFatal(e.Exception);
        };
        TaskScheduler.UnobservedTaskException += (_, e) =>
        {
            WriteCrash(e.Exception);
            e.SetObserved();
        };
        // Themes are set per window (ThemedWindows), never here: Application.RequestedTheme can't change later.
        _theme = Option("--theme");
        _demo = _args.Contains("--demo") || Option("--show") is not null;
        string lang = Option("--lang") ?? (System.Globalization.CultureInfo.CurrentUICulture.TwoLetterISOLanguageName is "nb" or "no" or "nn" ? "nb" : "en");
        _s = new ReswStrings(Path.Combine(AppContext.BaseDirectory, "Strings", lang == "nb" ? "nb-NO" : "en-US", "Resources.resw"), lang);
        InitializeComponent();
    }

    private string? Option(string name)
    {
        int i = Array.IndexOf(_args, name);
        return i >= 0 && i + 1 < _args.Length ? _args[i + 1] : null;
    }

    private static bool IsFatal(Exception? e) =>
        e is OutOfMemoryException or StackOverflowException or AccessViolationException or AppDomainUnloadedException
            or System.Runtime.InteropServices.SEHException or BadImageFormatException or InvalidProgramException;

    private static void WriteCrash(Exception? e)
    {
        try
        {
            var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Brasscribe", "logs");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "bandroom-crash.log"), $"{DateTimeOffset.Now:O} {e}{Environment.NewLine}");
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        _ui = DispatcherQueue.GetForCurrentThread();
        StartAppearance();
        _vm = new FlyoutViewModel(_s, this, this);
        _vm.PropertyChanged += (_, e) =>
        {
            if (e.PropertyName == nameof(FlyoutViewModel.View) && _vm.View == FlyoutView.Devices && _controller is not null)
                _ = _controller.RefreshDevicesAsync();
        };

        try
        {
            _tray = new TrayIcon();
            _tray.Activated += () => _ui.TryEnqueue(ToggleFlyout);
            _tray.KeyActivated += () => _ui.TryEnqueue(OpenFlyout);
            _tray.ContextMenuRequested += (x, y) => _ui.TryEnqueue(() => ShowTrayMenu(x, y));
        }
        catch (Exception e) when (e is System.Runtime.InteropServices.COMException or DllNotFoundException or EntryPointNotFoundException)
        {
            WriteCrash(e); // no notification area: the window form still works
        }

        _flyout = new FlyoutWindow(new BandroomPanel(_vm, this), () => _tray?.Bounds(), _themes);
        _flyout.Opened += () => { if (_controller is not null) { _controller.FlyoutOpen = true; _ = _controller.TickAsync(); } };
        _flyout.Closed2 += () => { if (_controller is not null) _controller.FlyoutOpen = false; };
        _flyout.EscapedToIcon += () => _tray?.Focus();

        AppInstance.GetCurrent().Activated += (_, _) => _ui.TryEnqueue(OpenWindow);

        if (_demo) StartDemo();
        else StartForReal();

        // Opened from the Start menu (not the sign-in start): show the window form, since the icon may be hidden.
        bool background = _args.Contains("--background")
            || AppInstance.GetCurrent().GetActivatedEventArgs().Kind == ExtendedActivationKind.StartupTask;
        if (!_demo && !background) OpenWindow();
    }

    /// <summary>
    /// Settings › Appearance (design/system.md §10): stored on this PC, applied to every window at once. A
    /// Windows contrast theme always wins; the choice is kept for when it's turned off.
    /// </summary>
    private void StartAppearance()
    {
        _accessibility = new Windows.UI.ViewManagement.AccessibilitySettings();
        AppearanceChoice? forced = _theme is null ? null : AppearanceRules.Parse(_theme);
        // Sample-content runs never touch the user's stored choice.
        var store = _demo ? null : new AppearanceStore(_paths.AppearanceFile);
        _appearance = new AppearanceViewModel(_s, store, _accessibility.HighContrast, forced);
        _themes = new ThemedWindows(_appearance.Resolved);
        _appearance.ThemeChanged += _themes.Set;
        _accessibility.HighContrastChanged += (_, _) => _ui.TryEnqueue(() => _appearance.HighContrast = _accessibility.HighContrast);
    }

    // ----- Real mode -----

    private void StartForReal()
    {
        _log = new EngineLog(_paths.Logs);
        _log.Write($"bandroom: starting, data folder {_paths.DataDir}");
        string token = AdminCredential.LoadOrCreate(_paths.AdminTokenFile);
        var gpus = Machine.GraphicsAdapters();
        var cudaGpu = EnvironmentPlan.CudaAdapter(gpus);
        _cuda = cudaGpu is not null;
        foreach (var g in gpus) _log.Write($"bandroom: graphics {g.Description} vendor 0x{g.VendorId:X4} driver {g.DriverVersion} (NVIDIA {g.NvidiaDriver})");
        string pixi = FindPixi();
        string bundled = Environment.GetEnvironmentVariable("BRASSCRIBE_BANDROOM_WORKSPACE") is { Length: > 0 } w ? w : Path.Combine(AppContext.BaseDirectory, "workspace");
        _nameStore = new ComputerNameStore(_paths.ComputerNameFile);
        _customName = _nameStore.Load();
        string computer = ComputerName.Shown(_systemName, _customName);
        string? band = EngineLaunchConfig.FindBandSounds(AppContext.BaseDirectory);
        _log.Write(band is null
            ? "bandroom: band sounds missing next to the exe (band\\brasscribe-band.sf2); Studio plays General MIDI sounds"
            : $"bandroom: band sounds {band}");
        _config = new EngineLaunchConfig(_paths, pixi, computer, token, _cuda, band) { HuggingFaceToken = HuggingFaceKey.Read };
        _hub = ModelCatalog.HubCache();
        _downloads = new ModelDownloader(_paths.Models, _hub, HuggingFaceKey.Current) { Log = _log.Write };
        _downloads.Changed += () => _controller?.Publish();
        _downloads.Completed += () => _ui.TryEnqueue(() =>
        {
            var models = _controller?.CheckModels();
            if (models?.IsReady == true) Announce(_s["Notify_Ready"]);
            // The separators came without a key: ask for it now (a run that fails never completes, so no loop).
            else if (models?.Missing is [ModelComponent.BandWriter] && HuggingFaceKey.Current() is null) _downloads.Start([ModelComponent.BandWriter]);
            _controller?.Publish();
        });

        _launcher = new JobObjectLauncher(_log.Write);
        _bootstrap = new Bootstrapper(_paths, bundled, pixi, _launcher, _log);
        var http = new HttpClient { Timeout = TimeSpan.FromSeconds(4) };
        IEngineApi ApiFor(int port) => new EngineApi(http, new Uri($"http://127.0.0.1:{port}/"), token);
        _supervisor = new EngineSupervisor(_launcher, new TcpPortProbe(),
            async (port, ct) => await ApiFor(port).GetHealthAsync(ct), port => _config!.Build(port), _log,
            options: new SupervisorOptions { StatusFilePath = _paths.StatusFile });

        string runsOn = cudaGpu is { } gpu ? $"CUDA 12 · {gpu.Description}" : "CPU";
        _controller = new BandroomController(_supervisor, ApiFor, new WindowsMetrics(), _s, _paths,
            new MachineInfo(computer, _cuda ? "Health_Speed_Nvidia" : "Health_Speed_Cpu", runsOn, Machine.LanAddresses()))
        {
            CheckModels = () => ModelCheck.Check(_paths.Models, _hub),
            Downloads = _downloads,
            Log = _log.Write,
        };
        _controller.SnapshotReady += snap => _ui.TryEnqueue(() => ApplySnapshot(snap));
        _controller.DevicesChanged += list => _ui.TryEnqueue(() => _vm.ApplyDevices(list, DateTimeOffset.UtcNow));
        _controller.Requests.Arrived += r => _ui.TryEnqueue(() => OnPairRequest(r));
        _controller.Requests.Gone += id => _ui.TryEnqueue(() => OnPairRequestGone(id));

        FirstRunDefaults();
        _ = RunAsync();
    }

    private async Task RunAsync()
    {
        var controller = _controller!;
        bool polling = false;
        try
        {
            // Hashes pixi.lock and the bundled workspace: off the UI thread, before the first snapshot.
            var bootstrap = _bootstrap!;
            await Task.Run(bootstrap.RecoverInterruptedUpdate);
            bool complete = await bootstrap.IsCompleteAsync(_cuda);
            controller.WorkspaceStamp = await Task.Run(() => bootstrap.BundleStamp.Short);
            // An engine that ran before, with another build of the workspace: the app was updated (§3.8).
            bool update = !complete && await Task.Run(() => bootstrap.IsUpdate);
            controller.SetupComplete = complete || update;
            _ = controller.RunAsync(_quit.Token);
            polling = true;
            if (update) await _setup.RunAsync(UpdateAsync);
            else if (!complete) await _setup.RunAsync(SetupAsync);
            else await _supervisor!.StartAsync();
        }
        catch (OperationCanceledException) when (_quit.IsCancellationRequested) { }
        catch (Exception e)
        {
            SetupStopped(e);
            if (!polling) _ = controller.RunAsync(_quit.Token);
        }
    }

    /// <summary>Setup or an update stopped on something unexpected: logged, and shown as a problem with Finish setting up.</summary>
    private void SetupStopped(Exception e)
    {
        _log?.Write("bandroom: setup stopped: " + e);
        if (_controller is not { } controller) return;
        controller.SetupFailure = e.Message;
        controller.Publish();
    }

    /// <summary>
    /// After an app update: stop the engine, replace the workspace (pixi install only for a new lockfile), start it
    /// again. A failure keeps the previous engine, which starts, with a Needs-attention problem and Try again.
    /// </summary>
    private async Task UpdateAsync()
    {
        if (_controller is not { } controller || _supervisor is not { } supervisor || _bootstrap is not { } bootstrap) return;
        controller.Updating = true;
        controller.UpdateFailure = null;
        controller.SetupFailure = null;
        controller.SetupFraction = 0;
        controller.Publish();
        await supervisor.StopAsync();
        var progress = new Progress<BootstrapProgress>(p =>
        {
            controller.SetupFraction = p.Fraction;
            // The engine environment is in: start it while the adapters update.
            if (p.EngineCurrent && supervisor.State == EngineState.Stopped)
            {
                controller.Updating = false;
                _ = supervisor.StartAsync();
            }
            controller.Publish();
        });
        try
        {
            await Task.Run(() => bootstrap.RunAsync(_cuda, progress, _quit.Token));
            _log?.Write("bandroom: engine workspace updated to " + controller.WorkspaceStamp);
        }
        catch (OperationCanceledException) { return; }
        catch (Exception e)
        {
            _log?.Write("bandroom: update stopped: " + e);
            // Still the old workspace: say so. A new one whose adapters stopped resumes like setup does.
            if (!await Task.Run(() => bootstrap.WorkspaceCurrent)) controller.UpdateFailure = e.Message;
        }
        finally { controller.Updating = false; }
        if (await Task.Run(() => bootstrap.EngineReady)) await supervisor.StartAsync();
        controller.Publish();
    }

    /// <summary>First run: the engine environment first, then start it, then the adapters in the background.</summary>
    private async Task SetupAsync()
    {
        _controller!.SetupFailure = null;
        var progress = new Progress<BootstrapProgress>(p =>
        {
            _controller!.SetupFraction = p.Fraction;
            _controller.Publish();
            if (p.EngineCurrent && _supervisor!.State == EngineState.Stopped)
                _ = _supervisor.StartAsync();
        });
        try
        {
            await Task.Run(() => _bootstrap!.RunAsync(_cuda, progress, _quit.Token));
            _controller!.SetupComplete = true;
            await _supervisor!.StartAsync();
            // The environments don't hold the model weights: fetch those now.
            StartMissingDownloads();
        }
        catch (OperationCanceledException) { }
        catch (Exception e)
        {
            SetupStopped(e);
            if (await Task.Run(() => _bootstrap!.EngineReady)) await _supervisor!.StartAsync();
        }
        _controller!.Publish();
    }

    private static string FindPixi()
    {
        var bundled = Path.Combine(AppContext.BaseDirectory, "pixi", "pixi.exe");
        if (File.Exists(bundled)) return bundled;
        var home = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".pixi", "bin", "pixi.exe");
        if (File.Exists(home)) return home;
        return "pixi.exe";
    }

    private void FirstRunDefaults()
    {
        var marker = Path.Combine(_paths.State, "first-run");
        if (File.Exists(marker)) return;
        try
        {
            if (_startup.Changeable) _startup.Enabled = true; // "Start when I log in" is on by default (§3.2 step 4)
            Directory.CreateDirectory(_paths.State);
            File.WriteAllText(marker, DateTimeOffset.Now.ToString("O"));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.Security.SecurityException) { _log?.Write(e.Message); }
    }

    private bool _trayLogged;

    private void ApplySnapshot(BandroomSnapshot snap)
    {
        _vm.Apply(snap);
        _tray?.Update(_vm.Badge, _vm.PieEighths, _vm.Tooltip);
        if (_restartWhenIdle && !_vm.IsBusy && _supervisor?.State == EngineState.Running)
        {
            _restartWhenIdle = false;
            _ = _supervisor.RestartAsync();
        }
        if (!_trayLogged && _tray is not null)
        {
            _trayLogged = true;
            _log?.Write(_tray.IsShown ? "bandroom: notification-area icon added" : "bandroom: notification-area icon failed: " + _tray.LastError);
        }
        KeepAwake.Set(_vm.IsBusy);
    }

    // ----- Demo mode: screenshots and the accessibility scan -----

    private void StartDemo()
    {
        _demoEngine = new DemoEngine();
        var state = Option("--state") ?? "running";
        ApplySnapshot(DemoEngine.Snapshot(state, _s));
        _vm.ApplyDevices(_demoEngine.Devices, DateTimeOffset.UtcNow);
        string show = Option("--show") ?? "flyout";
        _ui.TryEnqueue(DispatcherQueuePriority.Low, async () =>
        {
            switch (show)
            {
                case "flyout":
                    _flyout!.Pinned = true;
                    _flyout.ShowFlyout();
                    break;
                case "devices":
                    _flyout!.Pinned = true;
                    _flyout.ShowFlyout();
                    _vm.ShowDevicesCommand.Execute(null);
                    break;
                case "confirm-stop":
                    ApplySnapshot(DemoEngine.Snapshot("busy", _s));
                    _flyout!.Pinned = true;
                    _flyout.ShowFlyout();
                    await _vm.StopCommand.ExecuteAsync(null);
                    break;
                case "window":
                    OpenWindow();
                    break;
                case "pair":
                    OpenPairWindow();
                    break;
                case "allow":
                    OpenPairWindow();
                    OnPairRequest(_demoEngine.AddRequest());
                    break;
                case "settings":
                    OpenSettings();
                    break;
            }
        });
    }

    // ----- The icon, the flyout, the windows -----

    private void ToggleFlyout()
    {
        if (_flyout is null) return;
        if (_flyout.IsOpen) { _flyout.HideFlyout(); return; }
        // A click on the icon first takes focus from the flyout, which hides it: don't reopen at once.
        if ((DateTime.UtcNow - _flyout.HiddenAt).TotalMilliseconds < 300) return;
        // Past 150 % text size the flyout can't hold the content: open the window instead (§9, 1.4.4).
        if (new Windows.UI.ViewManagement.UISettings().TextScaleFactor > 1.5) { OpenWindow(); return; }
        _flyout.ShowFlyout();
    }

    /// <summary>Enter on the icon: open (or bring back) the flyout, never close it.</summary>
    private void OpenFlyout()
    {
        if (_flyout is null || _flyout.IsOpen) { _flyout?.Activate(); return; }
        if (new Windows.UI.ViewManagement.UISettings().TextScaleFactor > 1.5) { OpenWindow(); return; }
        _flyout.ShowFlyout();
    }

    private void OpenWindow()
    {
        if (_window is null)
        {
            _window = new PanelWindow(new BandroomPanel(_vm, this), _s["WindowTitle"], _themes);
            _window.Closed += (_, _) => _window = null;
        }
        _window.Activate();
        if (_controller is not null) { _controller.FlyoutOpen = true; _ = _controller.TickAsync(); }
    }

    private void ShowTrayMenu(int x, int y)
    {
        if (_tray is null) return;
        bool running = _supervisor?.State is EngineState.Running or EngineState.Starting || _demo;
        var items = new List<(int, string?, bool)>
        {
            (1, _s["Tray_Open"], true),
            (2, _s["Primary_Pair"], running),
            (0, null, true),
            (3, _s["Action_Restart"], running),
            (4, _s["Action_Stop"], running),
            (0, null, true),
        };
        // No setup window on Windows: the model download pauses and resumes here.
        if (_downloads is { IsActive: true }) items.AddRange([(6, _s["Tray_PauseDownloads"], true), (0, null, true)]);
        else if (_downloads is { Phase: DownloadPhase.Paused }) items.AddRange([(7, _s["Tray_ResumeDownloads"], true), (0, null, true)]);
        items.Add((5, _s["More_Quit"], true));
        int chosen = _tray.ShowMenu(x, y, [.. items]);
        switch (chosen)
        {
            case 1: _flyout?.ShowFlyout(); break;
            case 2: OpenPairWindow(); break;
            case 3: _vm.RestartCommand.Execute(null); if (_vm.IsConfirmView) _flyout?.ShowFlyout(); break;
            case 4: _vm.StopCommand.Execute(null); if (_vm.IsConfirmView) _flyout?.ShowFlyout(); break;
            case 5: Quit(); break;
            case 6: _downloads?.Pause(); break;
            case 7: _downloads?.Resume(); break;
        }
    }

    private IEngineApi? CurrentApi => _demoEngine ?? _controller?.Api;

    public void OpenPairWindow()
    {
        _flyout?.HideFlyout();
        if (_pairWindow is null)
        {
            var pair = new PairViewModel(_s, () => CurrentApi, this);
            _pairWindow = new PairWindow(pair, _themes);
            _pairWindow.Closed += (_, _) => _pairWindow = null;
            _ = pair.OpenAsync();
        }
        _pairWindow.Activate();
    }

    /// <summary>A phone chose this computer: in the Pair window if it is open, else in its own Allow window.</summary>
    private void OnPairRequest(PairRequestInfo r)
    {
        Task<PairDecision> Decide(string id, bool ok) => _demoEngine is not null
            ? _demoEngine.DecidePairRequestAsync(id, ok).ContinueWith(t => PairDecision.Done, TaskScheduler.Default)
            : CurrentApi is { } api && _controller is not null ? _controller.Requests.DecideAsync(api, id, ok) : Task.FromResult(PairDecision.Failed);

        if (_pairWindow is not null)
        {
            _pairWindow.Vm.AddRequest(r, Decide);
            _pairWindow.Activate();
            return;
        }
        if (_allowWindows.ContainsKey(r.RequestId)) return;
        var pair = new PairViewModel(_s, () => CurrentApi, this);
        var vm = pair.AddRequest(r, Decide);
        var w = new AllowWindow(vm, vm.Title, _themes);
        _allowWindows[r.RequestId] = vm;
        w.Closed += (_, _) => _allowWindows.Remove(r.RequestId);
        w.Activate();
        Announce(_s.Format("Notify_PairRequest", r.Name));
    }

    /// <summary>A request lapsed or was answered elsewhere: whichever window shows it says so.</summary>
    private void OnPairRequestGone(string id)
    {
        _pairWindow?.Vm.RequestGone(id);
        if (_allowWindows.TryGetValue(id, out var vm) && vm.IsActive) vm.MarkExpired();
    }

    // ----- IBandroomActions -----

    public Task StartAsync() => _supervisor?.StartAsync() ?? Task.CompletedTask;
    public Task StopAsync() => _supervisor?.StopAsync() ?? Task.CompletedTask;
    public Task RestartAsync() => _supervisor?.RestartAsync() ?? Task.CompletedTask;

    public void OpenStudio()
    {
        int? port = _supervisor?.Port ?? (_demo ? 8765 : null);
        if (port is { } p) _ = Windows.System.Launcher.LaunchUriAsync(new Uri($"http://127.0.0.1:{p}/"));
    }

    public void ShowLogs()
    {
        var file = _log?.FilePath ?? Path.Combine(_paths.Logs, "engine.log");
        if (File.Exists(file)) Process.Start(new ProcessStartInfo("explorer.exe", $"/select,\"{file}\"") { UseShellExecute = true });
        else if (Directory.Exists(_paths.Logs)) Process.Start(new ProcessStartInfo("explorer.exe", $"\"{_paths.Logs}\"") { UseShellExecute = true });
    }

    public void CopyText(string text)
    {
        var package = new Windows.ApplicationModel.DataTransfer.DataPackage();
        package.SetText(text);
        Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(package);
    }

    /// <summary>
    /// The environments first if they aren't all installed; else only the model downloads still missing. While setup
    /// or an update runs, asking again joins it.
    /// </summary>
    public void FinishSetup()
    {
        if (_bootstrap is not { } bootstrap || _controller is null) return;
        _ = _setup.RunAsync(() => FinishSetupAsync(bootstrap));
    }

    private async Task FinishSetupAsync(Bootstrapper bootstrap)
    {
        try
        {
            if (_controller is { } controller) controller.SetupFailure = null;
            if (await bootstrap.IsCompleteAsync(_cuda))
            {
                // Setup is done but the start may have stopped short: start it (nothing happens if it runs).
                await _supervisor!.StartAsync();
                StartMissingDownloads();
                _controller?.Publish();
            }
            else if (await Task.Run(() => bootstrap.IsUpdate)) await UpdateAsync();
            else await SetupAsync();
        }
        catch (Exception e) when (e is not OperationCanceledException) { SetupStopped(e); }
    }

    /// <summary>
    /// Fetches what ModelCheck finds missing. Without a Hugging Face key the separators still come; the band
    /// writer then asks for the key on its own.
    /// </summary>
    private void StartMissingDownloads()
    {
        if (_downloads is null || _controller is null || _downloads.IsActive) return;
        var missing = _controller.CheckModels().Missing;
        if (HuggingFaceKey.Current() is null && missing.Any(c => !c.NeedsHuggingFaceKey()))
            missing = missing.Where(c => !c.NeedsHuggingFaceKey()).ToList();
        if (missing.Count == 0) return;
        _log?.Write($"bandroom: downloading {string.Join(", ", missing)}");
        _downloads.Start(missing);
    }

    public void Fix(ProblemKind problem)
    {
        // Setup stopped: Finish setting up runs it again, whatever a download says meanwhile.
        if (problem == ProblemKind.MissingDownload && _controller?.SetupFailure is not null) { FinishSetup(); return; }
        string? uri = problem switch
        {
            ProblemKind.LowDisk => "ms-settings:storagesense",
            ProblemKind.PublicNetwork => "ms-settings:network-status",
            ProblemKind.MissingDownload => _downloads?.Error switch
            {
                DownloadError.LicenceNotAccepted => ModelComponent.BandWriter.Page().AbsoluteUri,
                DownloadError.NotEnoughSpace => "ms-settings:storagesense",
                _ => null,
            },
            _ => null,
        };
        if (uri is not null) _ = Windows.System.Launcher.LaunchUriAsync(new Uri(uri));
        else if (problem == ProblemKind.KeyRefused || (problem == ProblemKind.MissingDownload && _downloads?.Error is DownloadError.KeyMissing)) OpenSettings();
        else if (problem is ProblemKind.MissingDownload or ProblemKind.UpdateFailed) FinishSetup();
    }

    public async Task<bool> RemoveDeviceAsync(string deviceId)
    {
        if (CurrentApi is not { } api) return false;
        try
        {
            await api.RemoveDeviceAsync(deviceId);
            return true;
        }
        catch (Exception e) when (e is HttpRequestException or EngineHttpException or TaskCanceledException or System.Text.Json.JsonException)
        {
            _log?.Write("bandroom: removing a device: " + e.Message);
            return false;
        }
    }

    // ----- IPanelHost -----

    public bool StartAtLogin
    {
        get { try { return _startup.Enabled; } catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.Security.SecurityException) { return false; } }
        set { try { _startup.Enabled = value; } catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.Security.SecurityException) { _log?.Write(e.Message); } }
    }

    public bool StartAtLoginChangeable => _startup.Changeable;

    public void OpenSettings()
    {
        _flyout?.HideFlyout();
        if (_settingsWindow is null)
        {
            _settingsWindow = new SettingsWindow(_appearance, this, this, _s, _themes);
            _settingsWindow.Closed += (_, _) => _settingsWindow = null;
        }
        _settingsWindow.Activate();
    }

    public void OpenRemoveSettings() => _ = Windows.System.Launcher.LaunchUriAsync(new Uri("ms-settings:appsfeatures"));

    // ----- ISettingsHost -----

    public string SystemComputerName => _systemName;
    public string? CustomComputerName => _customName;

    public void SetCustomComputerName(string? name)
    {
        string? custom = string.IsNullOrWhiteSpace(name) ? null : name.Trim();
        if (custom == _customName) return;
        _customName = custom;
        // Sample-content runs keep the name in memory only.
        if (_nameStore is not null && !_nameStore.Save(custom)) _log?.Write("bandroom: couldn't save the name shown to phones");
        string shown = ComputerName.Shown(_systemName, custom);
        if (_config is not null) _config = _config with { ComputerName = shown };
        if (_controller is not null)
        {
            _controller.Machine = _controller.Machine with { ComputerName = shown };
            _controller.Publish();
        }
        RestartWhenIdle();
    }

    public bool HuggingFaceKeyFromEnvironment => HuggingFaceKey.FromEnvironment() is not null;
    public bool HuggingFaceKeySaved => !_demo && HuggingFaceKey.Read() is not null;

    public bool SaveHuggingFaceKey(string key)
    {
        if (_demo) return true;
        if (!HuggingFaceKey.Save(key)) { _log?.Write("bandroom: Credential Manager refused the Hugging Face key"); return false; }
        _log?.Write("bandroom: Hugging Face key saved");
        // A download that stopped for the key continues with it; the engine gets it as HF_TOKEN.
        if (_downloads is { Phase: DownloadPhase.Failed or DownloadPhase.Idle or DownloadPhase.Done }) StartMissingDownloads();
        RestartWhenIdle();
        return true;
    }

    public void OpenModelPage() => _ = Windows.System.Launcher.LaunchUriAsync(ModelComponent.BandWriter.Page());

    /// <summary>Restarts a running engine now if nothing is being made, else once the score is done.</summary>
    private void RestartWhenIdle()
    {
        if (_supervisor?.State != EngineState.Running) return; // the next start reads the new settings
        if (_vm.IsBusy) _restartWhenIdle = true;
        else _ = _supervisor.RestartAsync();
    }

    public async void Quit()
    {
        _quit.Cancel();
        _downloads?.Pause(); // the .part files stay for the next start
        if (_supervisor is not null) await _supervisor.StopAsync();
        _downloads?.Dispose();
        _launcher?.Dispose();
        _tray?.Dispose();
        KeepAwake.Set(false);
        Exit();
    }

    // ----- IAnnouncer -----

    public void Announce(string text)
    {
        _ui.TryEnqueue(() =>
        {
            if (_flyout?.IsOpen == true && _flyout.Content is FrameworkElement f && FindPanel(f) is { } p) p.Announce(text);
            else _window?.Panel.Announce(text);
        });
    }

    private static BandroomPanel? FindPanel(FrameworkElement root) =>
        root is Microsoft.UI.Xaml.Controls.Panel panel
            ? panel.Children.OfType<Microsoft.UI.Xaml.Controls.ScrollViewer>().Select(s => s.Content as BandroomPanel).FirstOrDefault()
            : null;
}
