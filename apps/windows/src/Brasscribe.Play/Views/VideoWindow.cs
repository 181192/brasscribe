using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Windows.Media.Playback;

namespace Brasscribe.Play.Views;

/// <summary>
/// The original video in a compact overlay window (picture-in-picture) that stays on top while the
/// user reads the score. It borrows the MediaPlayer from the score screen and gives it back on close.
/// </summary>
public sealed class VideoWindow : Window
{
    private readonly MediaPlayerElement _element = new() { AreTransportControlsEnabled = false, Stretch = Microsoft.UI.Xaml.Media.Stretch.Uniform };

    public VideoWindow(MediaPlayer player, string title)
    {
        Title = title;
        AutomationProperties.SetName(_element, title);
        _element.SetMediaPlayer(player);
        Content = _element;
        AppWindow.SetPresenter(AppWindowPresenterKind.CompactOverlay);
        AppWindow.Resize(new Windows.Graphics.SizeInt32(480, 270));
    }

    /// <summary>Releases the player so the score screen can show it again.</summary>
    public void Detach() => _element.SetMediaPlayer(null);
}
