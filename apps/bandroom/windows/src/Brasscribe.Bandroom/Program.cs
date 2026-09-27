using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.Windows.AppLifecycle;

namespace Brasscribe.Bandroom;

/// <summary>
/// One Bandroom per user: a second start (from the Start menu while it runs in the taskbar corner)
/// hands its activation to the running one, which opens "Brasscribe on this PC".
/// </summary>
public static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        WinRT.ComWrappersSupport.InitializeComWrappers();
        // Screenshot and scan runs (--show) are independent of any Bandroom already running.
        if (!args.Contains("--show"))
        {
            var key = AppInstance.FindOrRegisterForKey("BrasscribeBandroom");
            if (!key.IsCurrent)
            {
                var activation = AppInstance.GetCurrent().GetActivatedEventArgs();
                Task.Run(() => key.RedirectActivationToAsync(activation).AsTask()).Wait(TimeSpan.FromSeconds(10));
                return 0;
            }
        }
        Application.Start(p =>
        {
            var context = new DispatcherQueueSynchronizationContext(DispatcherQueue.GetForCurrentThread());
            SynchronizationContext.SetSynchronizationContext(context);
            _ = new App();
        });
        return 0;
    }
}
