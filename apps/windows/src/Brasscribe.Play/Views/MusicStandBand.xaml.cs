using Brasscribe.Play.Core.ViewModels;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Brasscribe.Play.Views;

/// <summary>The music stand's band at the top: where you are, and Leave.</summary>
public sealed partial class MusicStandBand : UserControl
{
    public MusicStandBand() => InitializeComponent();

    public ScoreViewModel? Score { get; private set; }

    public void Show(ScoreViewModel score)
    {
        Score = score;
        Bindings.Update();
    }

    /// <summary>The Leave button (the first stop when Tab goes into the stand's controls).</summary>
    public Control Leave => LeaveButton;

    /// <summary>The position text, which stays on screen for the whole stand: announcements are raised from it.</summary>
    public FrameworkElement Announcer => Position;

    private void OnLeave(object sender, RoutedEventArgs e) => Score?.Stand.Leave();
}
