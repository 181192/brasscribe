using System.Diagnostics;
using Brasscribe.Bandroom.Core;
using Brasscribe.Bandroom.Core.Appearance;
using Brasscribe.Bandroom.Core.Engine;
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
public partial class App : Application, IBandroomActions, IPanelHost, IAnnouncer
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

    public App()
    {
        AppDomain.CurrentDomain.UnhandledException += (_, e) => WriteCrash(e.ExceptionObject as Exception);
        UnhandledException += (_, e) => WriteCrash(e.Exception);
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
        string computer = Machine.ComputerName();
        var config = new EngineLaunchConfig(_paths, pixi, computer, token, _cuda);

        _launcher = new JobObjectLauncher();
        _bootstrap = new Bootstrapper(_paths, bundled, pixi, _launcher, _log);
        var http = new HttpClient { Timeout = TimeSpan.FromSeconds(4) };
        IEngineApi ApiFor(int port) => new EngineApi(http, new Uri($"http://127.0.0.1:{port}/"), token);
        _supervisor = new EngineSupervisor(_launcher, new TcpPortProbe(),
            async (port, ct) => await ApiFor(port).GetHealthAsync(ct), config.Build, _log,
            options: new SupervisorOptions { StatusFilePath = _paths.StatusFile });

        string runsOn = cudaGpu is { } gpu ? $"CUDA 12 · {gpu.Description}" : "CPU";
        _controller = new BandroomController(_supervisor, ApiFor, new WindowsMetrics(), _s, _paths,
            new MachineInfo(computer, _cuda ? "Health_Speed_Nvidia" : "Health_Speed_Cpu", runsOn, Machine.LanAddresses()))
        {
            SetupComplete = _bootstrap.IsComplete(_cuda),
            ModelsReady = () => _controller?.SetupComplete ?? false,
        };
        _controller.SnapshotReady += snap => _ui.TryEnqueue(() => ApplySnapshot(snap));
        _controller.DevicesChanged += list => _ui.TryEnqueue(() => _vm.ApplyDevices(list, DateTimeOffset.UtcNow));
        _controller.Requests.Arrived += r => _ui.TryEnqueue(() => OnPairRequest(r));
        _controller.Requests.Gone += id => _ui.TryEnqueue(() => _pairWindow?.Vm.RequestGone(id));

        FirstRunDefaults();
        _ = RunAsync();
    }

    private async Task RunAsync()
    {
        _ = _controller!.RunAsync(_quit.Token);
        if (!_bootstrap!.IsComplete(_cuda)) await SetupAsync();
        else await _supervisor!.StartAsync();
    }

    /// <summary>First run: the engine environment first, then start it, then the adapters in the background.</summary>
    private async Task SetupAsync()
    {
        var progress = new Progress<BootstrapProgress>(p =>
        {
            _controller!.SetupFraction = p.Fraction;
            _controller.Publish();
            if (p.Environment != "default" && p.Environment != "workspace" && _bootstrap!.EngineReady && _supervisor!.State == EngineState.Stopped)
                _ = _supervisor.StartAsync();
        });
        try
        {
            await Task.Run(() => _bootstrap!.RunAsync(_cuda, progress, _quit.Token));
            _controller!.SetupComplete = true;
            await _supervisor!.StartAsync();
        }
        catch (Exception e) when (e is BootstrapException or IOException or System.ComponentModel.Win32Exception or DirectoryNotFoundException)
        {
            _log?.Write("bandroom: setup stopped: " + e.Message);
            if (_bootstrap!.EngineReady) await _supervisor!.StartAsync();
        }
        catch (OperationCanceledException) { }
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
        int chosen = _tray.ShowMenu(x, y,
        [
            (1, _s["Tray_Open"], true),
            (2, _s["Primary_Pair"], running),
            (0, null, true),
            (3, _s["Action_Restart"], running),
            (4, _s["Action_Stop"], running),
            (0, null, true),
            (5, _s["More_Quit"], true),
        ]);
        switch (chosen)
        {
            case 1: _flyout?.ShowFlyout(); break;
            case 2: OpenPairWindow(); break;
            case 3: _vm.RestartCommand.Execute(null); if (_vm.IsConfirmView) _flyout?.ShowFlyout(); break;
            case 4: _vm.StopCommand.Execute(null); if (_vm.IsConfirmView) _flyout?.ShowFlyout(); break;
            case 5: Quit(); break;
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
        Task<bool> Decide(string id, bool ok) => _demoEngine is not null
            ? _demoEngine.DecidePairRequestAsync(id, ok).ContinueWith(t => true, TaskScheduler.Default)
            : CurrentApi is { } api && _controller is not null ? _controller.Requests.DecideAsync(api, id, ok) : Task.FromResult(false);

        if (_pairWindow is not null)
        {
            _pairWindow.Vm.AddRequest(r, Decide);
            _pairWindow.Activate();
            return;
        }
        var pair = new PairViewModel(_s, () => CurrentApi, this);
        var vm = pair.AddRequest(r, Decide);
        var w = new AllowWindow(vm, vm.Title, _themes);
        w.Activate();
        Announce(_s.Format("Notify_PairRequest", r.Name));
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

    public void FinishSetup()
    {
        if (_bootstrap is not null && _controller is not null && !_bootstrap.IsComplete(_cuda)) _ = SetupAsync();
    }

    public void Fix(ProblemKind problem)
    {
        string? uri = problem switch
        {
            ProblemKind.LowDisk => "ms-settings:storagesense",
            ProblemKind.PublicNetwork => "ms-settings:network-status",
            _ => null,
        };
        if (uri is not null) _ = Windows.System.Launcher.LaunchUriAsync(new Uri(uri));
        else if (problem == ProblemKind.MissingDownload) FinishSetup();
    }

    public async Task RemoveDeviceAsync(string deviceId)
    {
        if (CurrentApi is { } api)
        {
            try { await api.RemoveDeviceAsync(deviceId); }
            catch (Exception e) when (e is HttpRequestException or EngineHttpException or TaskCanceledException) { _log?.Write(e.Message); }
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
            _settingsWindow = new SettingsWindow(_appearance, this, _s, _themes);
            _settingsWindow.Closed += (_, _) => _settingsWindow = null;
        }
        _settingsWindow.Activate();
    }

    public void OpenRemoveSettings() => _ = Windows.System.Launcher.LaunchUriAsync(new Uri("ms-settings:appsfeatures"));

    public async void Quit()
    {
        _quit.Cancel();
        if (_supervisor is not null) await _supervisor.StopAsync();
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
