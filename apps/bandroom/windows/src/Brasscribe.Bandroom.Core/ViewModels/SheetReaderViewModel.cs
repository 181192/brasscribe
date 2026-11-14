using System.Globalization;
using Brasscribe.Bandroom.Core.Supervisor;
using CommunityToolkit.Mvvm.ComponentModel;

namespace Brasscribe.Bandroom.Core.ViewModels;

public enum SheetReaderState
{
    NotInstalled,
    Installing,
    Installed,
    Failed,
}

/// <summary>What the Settings card needs of this computer to install the reader of printed music.</summary>
public interface ISheetReaderHost
{
    /// <summary>An engine is installed and neither setup nor an update runs: there is a workspace to install into.</summary>
    bool CanInstall { get; }
    bool Installed { get; }
    /// <summary>Free bytes on the drive of the data folder.</summary>
    long FreeBytes { get; }
    /// <summary>Installs it (<see cref="Bootstrapper.InstallReaderAsync"/>); throws <see cref="SheetReaderException"/>.</summary>
    Task InstallAsync();
}

/// <summary>
/// The card in Settings for the reader of printed music (<see cref="SheetReader"/>): what it is, its licence and
/// where it comes from, shown before anything is fetched, and one button that fetches it. The reader is not part of
/// setup, so nothing here is a problem to fix: without it everything else works, and phones are not offered the
/// two profiles that read pages. One of these lives as long as the app, so closing Settings does not lose an
/// install under way.
/// </summary>
public sealed partial class SheetReaderViewModel : ObservableObject
{
    private readonly IStrings _s;
    private readonly ISheetReaderHost _host;
    private readonly IAnnouncer _announcer;

    public SheetReaderViewModel(IStrings strings, ISheetReaderHost host, IAnnouncer? announcer = null)
    {
        _s = strings;
        _host = host;
        _announcer = announcer ?? new NullAnnouncer();
        _state = host.Installed ? SheetReaderState.Installed : SheetReaderState.NotInstalled;
    }

    public string Header => _s["Settings_Reader"];

    /// <summary>What it does, what it is, and its licence.</summary>
    public string Body => _s["Settings_Reader_Body"];

    /// <summary>Where it comes from, how much it is, and that it runs as a program of its own.</summary>
    public string Source => _s.Format("Settings_Reader_Source", Gigabytes(SheetReader.DownloadBytes));

    /// <summary>The link to its makers' page.</summary>
    public string ReadMore => _s["Settings_Reader_Read"];

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(Status), nameof(Button), nameof(ShowsButton), nameof(CanInstall), nameof(IsInstalling), nameof(ShowsProgress), nameof(ShowsLogs))]
    private SheetReaderState _state;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(Status))]
    private string _failure = "";

    /// <summary>The button that shows the log, as in the panel's details.</summary>
    public string Logs => _s["Tech_Logs"];

    /// <summary>The failure shown is one whose words send the person to the log: the way there is beside them.</summary>
    public bool ShowsLogs => State == SheetReaderState.Failed && _detailsInLog;
    private bool _detailsInLog;

    /// <summary>The line under the description: installing, installed, or why it stopped. Empty before anything was asked for.</summary>
    public string Status => State switch
    {
        SheetReaderState.Installing => _s["Settings_Reader_Installing"],
        SheetReaderState.Installed => _s["Settings_Reader_Installed"],
        SheetReaderState.Failed => Failure,
        _ => _host.CanInstall ? "" : _s["Settings_Reader_Wait"],
    };

    public string Button => _s[State == SheetReaderState.Failed ? "Primary_TryAgain" : "Settings_Reader_Install"];
    public bool ShowsButton => State is SheetReaderState.NotInstalled or SheetReaderState.Failed;
    public bool CanInstall => ShowsButton && _host.CanInstall;
    public bool IsInstalling => State == SheetReaderState.Installing;

    /// <summary>The card shows sample content (<see cref="ShowSample"/>), not an install of this computer's.</summary>
    public bool IsSample { get; private set; }

    /// <summary>The progress bar runs while this computer installs; a sample of that state is drawn without it, so its picture keeps still.</summary>
    public bool ShowsProgress => IsInstalling && !IsSample;

    /// <summary>The states the screen catalogue asks for with <c>--state</c>, by name; null for any other.</summary>
    public static SheetReaderState? SampleState(string? name) => name switch
    {
        "reader-installing" => SheetReaderState.Installing,
        "reader-installed" => SheetReaderState.Installed,
        "reader-failed" => SheetReaderState.Failed,
        _ => null,
    };

    /// <summary>
    /// Sample content, for the screen catalogue: the card as it is while the reader installs, once it is there, or
    /// after an install that stopped with its details in the log (the failure with the most on the card: its words
    /// and the way to the log). Nothing is installed.
    /// </summary>
    public void ShowSample(SheetReaderState state)
    {
        IsSample = true;
        _detailsInLog = state == SheetReaderState.Failed;
        Failure = state == SheetReaderState.Failed ? _s["Settings_Reader_Failed"] : "";
        State = state;
        OnPropertyChanged(nameof(ShowsProgress));
    }

    /// <summary>Looks again (Settings was opened; setup finished): an install under way is left as it is.</summary>
    public void Refresh()
    {
        if (State == SheetReaderState.Installing) return;
        if (_host.Installed) State = SheetReaderState.Installed;
        else if (State == SheetReaderState.Installed) State = SheetReaderState.NotInstalled;
        OnPropertyChanged(nameof(Status));
        OnPropertyChanged(nameof(CanInstall));
    }

    /// <summary>The button: install, or try again. Never throws; a failure is the card's own line, with Try again.</summary>
    public async Task InstallAsync()
    {
        if (!CanInstall) { Refresh(); return; }
        long free = _host.FreeBytes;
        if (free < SheetReader.NeededFreeBytes)
        {
            Fail(_s.Format("Settings_Reader_Failed_Space", Gigabytes(SheetReader.NeededFreeBytes), Gigabytes(free)));
            return;
        }
        State = SheetReaderState.Installing;
        try
        {
            await _host.InstallAsync();
        }
        catch (OperationCanceledException)
        {
            State = SheetReaderState.NotInstalled; // Bandroom is quitting
            return;
        }
        catch (SheetReaderException e)
        {
            string key = e.Failure switch
            {
                SheetReaderFailure.Network => "Settings_Reader_Failed_Network",
                SheetReaderFailure.DiskFull => "Settings_Reader_Failed_Full",
                SheetReaderFailure.NotSetUp => "Settings_Reader_Wait",
                _ => "Settings_Reader_Failed",
            };
            Fail(_s[key], detailsInLog: key == "Settings_Reader_Failed");
            return;
        }
        catch (Exception)
        {
            // Whatever it was (pixi could not be started, the disk): it is in the log, and the card must not stay on Installing.
            Fail(_s["Settings_Reader_Failed"], detailsInLog: true);
            return;
        }
        if (!_host.Installed) { Fail(_s["Settings_Reader_Failed"], detailsInLog: true); return; }
        State = SheetReaderState.Installed;
        _announcer.Announce(Status);
    }

    private void Fail(string why, bool detailsInLog = false)
    {
        _detailsInLog = detailsInLog;
        Failure = why;
        State = SheetReaderState.Failed;
        _announcer.Announce(why);
    }

    /// <summary>"0.6", "0,6" in bokmål.</summary>
    private string Gigabytes(long bytes) => (bytes / 1_000_000_000.0).ToString("0.0", _s.Culture);
}
