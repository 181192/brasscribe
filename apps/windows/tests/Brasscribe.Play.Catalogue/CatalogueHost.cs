using Microsoft.Testing.Platform.Builder;
using Microsoft.UI.Xaml;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Microsoft.VisualStudio.TestTools.UnitTesting.AppContainer;

[assembly: DoNotParallelize]

namespace Brasscribe.Play;

/// <summary>
/// The app as the screen catalogue's test host: the Microsoft Testing Platform runs in this process, started from
/// OnLaunched, and the [UITestMethod] tests run on this app's UI thread. Only in the catalogue build
/// (-p:BrasscribeCatalogue=true); see tests/Brasscribe.Play.Catalogue/README.md.
/// </summary>
public partial class App
{
    static partial void RunCatalogue(App app, ref bool handled)
    {
        handled = true;
        // The run's language. Not --lang: the test platform runs the tests in a process of its own, started with the
        // platform's arguments only. Set before any window or string is made, as the app's constructor does.
        if (Environment.GetEnvironmentVariable("BRASSCRIBE_CATALOGUE_LANG") is { Length: > 0 } language)
        {
            Microsoft.Windows.Globalization.ApplicationLanguages.PrimaryLanguageOverride = language;
            var culture = System.Globalization.CultureInfo.GetCultureInfo(language);
            System.Globalization.CultureInfo.DefaultThreadCurrentCulture = culture;
            System.Globalization.CultureInfo.DefaultThreadCurrentUICulture = culture;
            System.Globalization.CultureInfo.CurrentCulture = culture;
            System.Globalization.CultureInfo.CurrentUICulture = culture;
        }
        // The screens come and go one window at a time: the app must not end when one closes.
        app.DispatcherShutdownMode = DispatcherShutdownMode.OnExplicitShutdown;
        Catalogue.ScreenCatalogue.App = app;
        UITestMethodAttribute.DispatcherQueue = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();
        _ = RunAsync(app);
    }

    private static async Task RunAsync(App app)
    {
        try
        {
            var builder = await TestApplication.CreateBuilderAsync(Environment.GetCommandLineArgs()[1..]);
            builder.AddMSTest(() => [typeof(App).Assembly]);
            Microsoft.Testing.Extensions.TrxReportExtensions.AddTrxReportProvider(builder);
            using var testApp = await builder.BuildAsync();
            // WinUI's generated entry point returns nothing: the exit code is set here.
            Environment.ExitCode = await testApp.RunAsync();
        }
        catch (Exception e)
        {
            Console.Error.WriteLine(e);
            Environment.ExitCode = 3;
        }
        finally
        {
            app.Exit();
        }
    }
}
