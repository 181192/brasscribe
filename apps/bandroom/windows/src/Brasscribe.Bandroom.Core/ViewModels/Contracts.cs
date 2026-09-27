using Brasscribe.Bandroom.Core.State;

namespace Brasscribe.Bandroom.Core.ViewModels;

/// <summary>Polite screen-reader announcements that don't move focus (4.1.3).</summary>
public interface IAnnouncer
{
    void Announce(string text);
}

/// <summary>What the flyout's buttons do outside the view model: the supervisor and the Windows shell.</summary>
public interface IBandroomActions
{
    Task StartAsync();
    Task StopAsync();
    Task RestartAsync();
    void OpenPairWindow();
    void OpenStudio();
    void ShowLogs();
    void CopyText(string text);
    void FinishSetup();
    void Fix(ProblemKind problem);
    Task RemoveDeviceAsync(string deviceId);
}

public sealed class NullAnnouncer : IAnnouncer
{
    public void Announce(string text) { }
}
